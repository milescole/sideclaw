"""Playwright-backed browser automation service."""

# ruff: noqa: BLE001, PIE810, PLR0911, PLW0108, PTH110, S110, S603, SIM112, TRY300

from __future__ import annotations

import asyncio
import atexit
import json
import logging
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from sideclaw.browser.snapshot import build_role_snapshot_from_aria

logger = logging.getLogger(__name__)

DEFAULT_COMMAND_TIMEOUT = 30
DEFAULT_INACTIVITY_TIMEOUT_SECONDS = 300
DEFAULT_OUTPUT_MAX_CHARS = 12_000
PLAYWRIGHT_CHROMIUM_ENV = "PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH"
_USE_SYNC_PLAYWRIGHT = sys.platform == "win32" and os.environ.get("SIDECLAW_RELOAD_MODE") == "1"

_executor: ThreadPoolExecutor | None = None


def _get_executor() -> ThreadPoolExecutor:
    global _executor
    if _executor is None:
        _executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="playwright")
    return _executor


def _is_running_in_container() -> bool:
    return os.path.exists("/.dockerenv")


def _normalize_console_level(level: str) -> str:
    level = (level or "").strip().lower()
    aliases = {
        "error": "error",
        "warning": "warning",
        "warn": "warning",
        "debug": "debug",
        "info": "info",
        "log": "info",
    }
    return aliases.get(level, "info")


def _new_session_state() -> dict[str, Any]:
    return {
        "playwright": None,
        "browser": None,
        "context": None,
        "pages": {},
        "refs": {},
        "refs_frame": {},
        "console_logs": {},
        "network_requests": {},
        "pending_dialogs": {},
        "pending_file_choosers": {},
        "headless": True,
        "current_page_id": None,
        "page_counter": 0,
        "last_activity_time": 0.0,
        "idle_task": None,
        "last_browser_error": None,
        "sync_browser": None,
        "sync_context": None,
        "sync_playwright": None,
    }


class BrowserService:
    """Manage browser state for one or more SideClaw sessions."""

    def __init__(
        self,
        workspace: Path,
        *,
        command_timeout: int = DEFAULT_COMMAND_TIMEOUT,
        inactivity_timeout_seconds: int = DEFAULT_INACTIVITY_TIMEOUT_SECONDS,
    ) -> None:
        self._workspace = Path(workspace)
        self._command_timeout = command_timeout
        self._inactivity_timeout_seconds = inactivity_timeout_seconds
        self._sessions: dict[str, dict[str, Any]] = {}
        atexit.register(self._atexit_cleanup)

    def requirements_met(self) -> bool:
        try:
            if _USE_SYNC_PLAYWRIGHT:
                self._ensure_playwright_sync()
            else:
                self._ensure_playwright_async()
        except ImportError:
            return False
        return True

    async def execute(self, task_id: str, **kwargs: Any) -> str:
        action = str(kwargs.get("action", "")).strip().lower()
        if not action:
            return self._json_error("action required")

        aliases = {
            "back": "navigate_back",
            "press": "press_key",
            "take_screenshot": "screenshot",
        }
        action = aliases.get(action, action)

        page_id = str(kwargs.get("page_id", "default") or "default").strip() or "default"
        state = self._get_state(task_id)
        current = state.get("current_page_id")
        pages = state.get("pages") or {}
        if page_id == "default" and current and current in pages:
            page_id = str(current)

        try:
            if action == "start":
                return await self._action_start(task_id, headed=bool(kwargs.get("headed", False)))
            if action == "stop":
                return await self._action_stop(task_id)
            if action == "open":
                return await self._action_open(task_id, str(kwargs.get("url", "")), page_id)
            if action == "navigate":
                return await self._action_navigate(task_id, str(kwargs.get("url", "")), page_id)
            if action == "navigate_back":
                return await self._action_navigate_back(task_id, page_id)
            if action == "screenshot":
                return await self._action_screenshot(
                    task_id,
                    page_id=page_id,
                    path=str(kwargs.get("path", "") or kwargs.get("filename", "")),
                    full_page=bool(kwargs.get("full_page", False)),
                    screenshot_type=str(kwargs.get("screenshot_type", "png")),
                    ref=str(kwargs.get("ref", "")),
                    frame_selector=str(kwargs.get("frame_selector", "")),
                )
            if action == "snapshot":
                return await self._action_snapshot(
                    task_id,
                    page_id=page_id,
                    filename=str(kwargs.get("snapshot_filename", "") or kwargs.get("filename", "")),
                    frame_selector=str(kwargs.get("frame_selector", "")),
                )
            if action == "click":
                return await self._action_click(
                    task_id,
                    page_id=page_id,
                    selector=str(kwargs.get("selector", "")),
                    ref=str(kwargs.get("ref", "")),
                    wait=int(kwargs.get("wait", 0) or 0),
                    double_click=bool(kwargs.get("double_click", False)),
                    button=str(kwargs.get("button", "left")),
                    modifiers_json=str(kwargs.get("modifiers_json", "")),
                    frame_selector=str(kwargs.get("frame_selector", "")),
                )
            if action == "type":
                return await self._action_type(
                    task_id,
                    page_id=page_id,
                    selector=str(kwargs.get("selector", "")),
                    ref=str(kwargs.get("ref", "")),
                    text=str(kwargs.get("text", "")),
                    submit=bool(kwargs.get("submit", False)),
                    slowly=bool(kwargs.get("slowly", False)),
                    frame_selector=str(kwargs.get("frame_selector", "")),
                )
            if action == "eval":
                return await self._action_eval(task_id, page_id, str(kwargs.get("code", "")))
            if action == "evaluate":
                return await self._action_evaluate(
                    task_id,
                    page_id=page_id,
                    code=str(kwargs.get("code", "")),
                    ref=str(kwargs.get("ref", "")),
                    frame_selector=str(kwargs.get("frame_selector", "")),
                )
            if action == "resize":
                return await self._action_resize(
                    task_id,
                    page_id=page_id,
                    width=int(kwargs.get("width", 0) or 0),
                    height=int(kwargs.get("height", 0) or 0),
                )
            if action == "console_messages":
                return await self._action_console_messages(
                    task_id,
                    page_id=page_id,
                    level=str(kwargs.get("level", "info")),
                    filename=str(kwargs.get("filename", "") or kwargs.get("path", "")),
                )
            if action == "handle_dialog":
                return await self._action_handle_dialog(
                    task_id,
                    page_id=page_id,
                    accept=bool(kwargs.get("accept", True)),
                    prompt_text=str(kwargs.get("prompt_text", "")),
                )
            if action == "file_upload":
                return await self._action_file_upload(
                    task_id,
                    page_id=page_id,
                    paths_json=str(kwargs.get("paths_json", "")),
                )
            if action == "fill_form":
                return await self._action_fill_form(
                    task_id,
                    page_id=page_id,
                    fields_json=str(kwargs.get("fields_json", "")),
                )
            if action == "install":
                return await self._action_install()
            if action == "press_key":
                return await self._action_press_key(
                    task_id,
                    page_id=page_id,
                    key=str(kwargs.get("key", "")),
                )
            if action == "network_requests":
                return await self._action_network_requests(
                    task_id,
                    page_id=page_id,
                    include_static=bool(kwargs.get("include_static", False)),
                    filename=str(kwargs.get("filename", "") or kwargs.get("path", "")),
                )
            if action == "run_code":
                return await self._action_run_code(task_id, page_id, str(kwargs.get("code", "")))
            if action == "drag":
                return await self._action_drag(
                    task_id,
                    page_id=page_id,
                    start_ref=str(kwargs.get("start_ref", "")),
                    end_ref=str(kwargs.get("end_ref", "")),
                    start_selector=str(kwargs.get("start_selector", "")),
                    end_selector=str(kwargs.get("end_selector", "")),
                    frame_selector=str(kwargs.get("frame_selector", "")),
                )
            if action == "hover":
                return await self._action_hover(
                    task_id,
                    page_id=page_id,
                    ref=str(kwargs.get("ref", "")),
                    selector=str(kwargs.get("selector", "")),
                    frame_selector=str(kwargs.get("frame_selector", "")),
                )
            if action == "select_option":
                return await self._action_select_option(
                    task_id,
                    page_id=page_id,
                    ref=str(kwargs.get("ref", "")),
                    values_json=str(kwargs.get("values_json", "")),
                    frame_selector=str(kwargs.get("frame_selector", "")),
                )
            if action == "tabs":
                return await self._action_tabs(
                    task_id,
                    page_id=page_id,
                    tab_action=str(kwargs.get("tab_action", "")),
                    index=int(kwargs.get("index", -1) or -1),
                )
            if action == "wait_for":
                return await self._action_wait_for(
                    task_id,
                    page_id=page_id,
                    wait_time=float(kwargs.get("wait_time", 0) or 0),
                    text=str(kwargs.get("text", "")),
                    text_gone=str(kwargs.get("text_gone", "")),
                )
            if action == "pdf":
                return await self._action_pdf(
                    task_id,
                    page_id=page_id,
                    path=str(kwargs.get("path", "")),
                )
            if action == "close":
                return await self._action_close(task_id, page_id)
            return self._json_error(f"unknown action '{action}'")
        except Exception as exc:  # pragma: no cover - defensive boundary
            logger.exception("browser tool error")
            return self._json_error(str(exc))

    def cleanup(self, task_id: str) -> None:
        state = self._sessions.get(task_id)
        if state is None:
            return
        self._cancel_idle_watchdog(state)
        if not self._is_browser_running(state):
            self._sessions.pop(task_id, None)
            return
        try:
            loop = asyncio.get_event_loop()
            if not loop.is_running() and not loop.is_closed():
                loop.run_until_complete(self._action_stop(task_id))
        except Exception:
            pass
        self._sessions.pop(task_id, None)

    def cleanup_all(self) -> None:
        for task_id in list(self._sessions):
            self.cleanup(task_id)

    def _atexit_cleanup(self) -> None:
        self.cleanup_all()

    def _get_state(self, task_id: str) -> dict[str, Any]:
        return self._sessions.setdefault(task_id, _new_session_state())

    def _touch_activity(self, state: dict[str, Any]) -> None:
        state["last_activity_time"] = time.monotonic()

    def _is_browser_running(self, state: dict[str, Any]) -> bool:
        if _USE_SYNC_PLAYWRIGHT:
            return state.get("sync_browser") is not None
        return state.get("browser") is not None

    def _reset_browser_state(self, state: dict[str, Any]) -> None:
        state.update(_new_session_state())

    async def _run_sync(self, func: Any, *args: Any, **kwargs: Any) -> Any:
        if _USE_SYNC_PLAYWRIGHT:
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(_get_executor(), lambda: func(*args, **kwargs))
        return await func(*args, **kwargs)

    def _chromium_launch_args(self) -> list[str]:
        if _is_running_in_container():
            return ["--no-sandbox", "--disable-dev-shm-usage"]
        return []

    def _chromium_executable_path(self) -> str | None:
        path = os.environ.get(PLAYWRIGHT_CHROMIUM_ENV)
        if path and Path(path).is_file():
            return path
        candidates = []
        if sys.platform == "darwin":
            candidates.extend(
                [
                    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                    "/Applications/Chromium.app/Contents/MacOS/Chromium",
                    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
                ]
            )
        elif sys.platform == "win32":
            program_files = os.environ.get("ProgramFiles", "C:\\Program Files")
            program_files_x86 = os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)")
            candidates.extend(
                [
                    f"{program_files}\\Google\\Chrome\\Application\\chrome.exe",
                    f"{program_files_x86}\\Google\\Chrome\\Application\\chrome.exe",
                    f"{program_files}\\Microsoft\\Edge\\Application\\msedge.exe",
                    f"{program_files_x86}\\Microsoft\\Edge\\Application\\msedge.exe",
                ]
            )
        else:
            candidates.extend(
                [
                    "/usr/bin/google-chrome",
                    "/usr/bin/google-chrome-stable",
                    "/usr/bin/chromium",
                    "/usr/bin/chromium-browser",
                    "/usr/lib/chromium/chromium",
                ]
            )
        for candidate in candidates:
            if Path(candidate).is_file():
                return str(Path(candidate))
        return None

    def _ensure_playwright_async(self) -> Any:
        try:
            from playwright.async_api import async_playwright
        except ImportError as exc:  # pragma: no cover - import guard
            msg = (
                "Playwright not installed. Install it with "
                f"'{sys.executable}' -m pip install playwright && "
                f"'{sys.executable}' -m playwright install"
            )
            raise ImportError(msg) from exc
        return async_playwright

    def _ensure_playwright_sync(self) -> Any:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:  # pragma: no cover - import guard
            msg = (
                "Playwright not installed. Install it with "
                f"'{sys.executable}' -m pip install playwright && "
                f"'{sys.executable}' -m playwright install"
            )
            raise ImportError(msg) from exc
        return sync_playwright

    def _sync_browser_launch(self, headless: bool) -> tuple[Any, Any, Any]:
        sync_playwright = self._ensure_playwright_sync()
        playwright = sync_playwright().start()
        executable_path = self._chromium_executable_path()
        launch_kwargs: dict[str, Any] = {"headless": headless}
        extra_args = self._chromium_launch_args()
        if extra_args:
            launch_kwargs["args"] = extra_args
        if executable_path:
            launch_kwargs["executable_path"] = executable_path
        browser = playwright.chromium.launch(**launch_kwargs)
        context = browser.new_context()
        return playwright, browser, context

    def _sync_browser_close(self, state: dict[str, Any]) -> None:
        if state.get("sync_browser") is not None:
            try:
                state["sync_browser"].close()
            except Exception:
                pass
        if state.get("sync_playwright") is not None:
            try:
                state["sync_playwright"].stop()
            except Exception:
                pass

    async def _idle_watchdog(self, task_id: str, idle_seconds: float) -> None:
        try:
            while True:
                await asyncio.sleep(60)
                state = self._sessions.get(task_id)
                if state is None or not self._is_browser_running(state):
                    return
                idle = time.monotonic() - float(state.get("last_activity_time", 0.0))
                if idle >= idle_seconds:
                    logger.info("browser idle for %.0fs, stopping session %s", idle, task_id)
                    await self._action_stop(task_id)
                    return
        except asyncio.CancelledError:  # pragma: no cover - background task
            return

    def _start_idle_watchdog(self, task_id: str, state: dict[str, Any]) -> None:
        self._cancel_idle_watchdog(state)
        state["idle_task"] = asyncio.ensure_future(
            self._idle_watchdog(task_id, float(self._inactivity_timeout_seconds))
        )

    def _cancel_idle_watchdog(self, state: dict[str, Any]) -> None:
        task = state.get("idle_task")
        if task and not task.done():
            task.cancel()
        state["idle_task"] = None

    async def _ensure_browser(self, task_id: str) -> bool:
        state = self._get_state(task_id)
        if self._is_browser_running(state):
            self._touch_activity(state)
            return True

        try:
            if _USE_SYNC_PLAYWRIGHT:
                loop = asyncio.get_event_loop()
                playwright, browser, context = await loop.run_in_executor(
                    _get_executor(),
                    lambda: self._sync_browser_launch(state["headless"]),
                )
                state["sync_playwright"] = playwright
                state["sync_browser"] = browser
                state["sync_context"] = context
            else:
                async_playwright = self._ensure_playwright_async()
                playwright = await async_playwright().start()
                launch_kwargs: dict[str, Any] = {"headless": state["headless"]}
                extra_args = self._chromium_launch_args()
                if extra_args:
                    launch_kwargs["args"] = extra_args
                executable_path = self._chromium_executable_path()
                if executable_path:
                    launch_kwargs["executable_path"] = executable_path
                browser = await playwright.chromium.launch(**launch_kwargs)
                context = await browser.new_context()
                state["playwright"] = playwright
                state["browser"] = browser
                state["context"] = context
            self._attach_context_listeners(task_id, state, context)
            state["last_browser_error"] = None
            self._touch_activity(state)
            self._start_idle_watchdog(task_id, state)
            return True
        except Exception as exc:
            state["last_browser_error"] = str(exc)
            return False

    def _parse_json_param(self, value: str, default: Any = None) -> Any:
        if not value or not isinstance(value, str):
            return default
        value = value.strip()
        if not value:
            return default
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            if "," in value:
                return [chunk.strip() for chunk in value.split(",") if chunk.strip()]
            return default

    def _workspace_path(self, raw_path: str, *, allow_empty: bool = False) -> Path | None:
        raw_path = raw_path.strip()
        if not raw_path:
            return None if allow_empty else self._workspace / "artifacts" / "browser"
        candidate = Path(raw_path).expanduser()
        if not candidate.is_absolute():
            candidate = self._workspace / candidate
        resolved = candidate.resolve(strict=False)
        workspace_root = self._workspace.resolve(strict=False)
        if resolved != workspace_root and workspace_root not in resolved.parents:
            msg = f"path must stay inside workspace: {resolved}"
            raise ValueError(msg)
        return resolved

    def _artifact_path(self, raw_path: str, default_filename: str) -> Path:
        if raw_path.strip():
            path = self._workspace_path(raw_path, allow_empty=True)
            assert path is not None
            path.parent.mkdir(parents=True, exist_ok=True)
            return path
        path = self._workspace / "artifacts" / "browser" / default_filename
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def _get_page(self, state: dict[str, Any], page_id: str) -> Any | None:
        return state["pages"].get(page_id)

    def _get_refs(self, state: dict[str, Any], page_id: str) -> dict[str, dict[str, Any]]:
        return state["refs"].setdefault(page_id, {})

    def _get_root(self, page: Any, frame_selector: str = "") -> Any:
        if not frame_selector.strip():
            return page
        return page.frame_locator(frame_selector.strip())

    def _get_locator_by_ref(
        self,
        state: dict[str, Any],
        page: Any,
        page_id: str,
        ref: str,
        frame_selector: str = "",
    ) -> Any | None:
        info = self._get_refs(state, page_id).get(ref)
        if not info:
            return None
        locator = self._get_root(page, frame_selector).get_by_role(
            info.get("role", "generic"), name=info.get("name")
        )
        nth = info.get("nth")
        if nth is not None and nth > 0:
            locator = locator.nth(nth)
        return locator

    def _attach_page_listeners(
        self,
        state: dict[str, Any],
        page_id: str,
        page: Any,
    ) -> None:
        logs = state["console_logs"].setdefault(page_id, [])

        def on_console(message: Any) -> None:
            logs.append({"level": _normalize_console_level(message.type), "text": message.text})

        requests = state["network_requests"].setdefault(page_id, [])

        def on_request(request: Any) -> None:
            requests.append(
                {
                    "method": request.method,
                    "resourceType": getattr(request, "resource_type", None),
                    "url": request.url,
                }
            )

        def on_response(response: Any) -> None:
            for item in requests:
                if item.get("url") == response.url and "status" not in item:
                    item["status"] = response.status
                    break

        dialogs = state["pending_dialogs"].setdefault(page_id, [])

        def on_dialog(dialog: Any) -> None:
            dialogs.append(dialog)

        choosers = state["pending_file_choosers"].setdefault(page_id, [])

        def on_filechooser(chooser: Any) -> None:
            choosers.append(chooser)

        page.on("console", on_console)
        page.on("request", on_request)
        page.on("response", on_response)
        page.on("dialog", on_dialog)
        page.on("filechooser", on_filechooser)

    def _next_page_id(self, state: dict[str, Any]) -> str:
        state["page_counter"] += 1
        return f"page_{state['page_counter']}"

    def _attach_context_listeners(self, task_id: str, state: dict[str, Any], context: Any) -> None:
        def on_page(page: Any) -> None:
            new_page_id = self._next_page_id(state)
            state["refs"][new_page_id] = {}
            state["console_logs"][new_page_id] = []
            state["network_requests"][new_page_id] = []
            state["pending_dialogs"][new_page_id] = []
            state["pending_file_choosers"][new_page_id] = []
            self._attach_page_listeners(state, new_page_id, page)
            state["pages"][new_page_id] = page
            state["current_page_id"] = new_page_id
            self._touch_activity(state)
            logger.debug("new browser tab for %s registered as %s", task_id, new_page_id)

        context.on("page", on_page)

    def _json(self, payload: dict[str, Any]) -> str:
        rendered = json.dumps(payload, ensure_ascii=False, indent=2)
        if len(rendered) <= DEFAULT_OUTPUT_MAX_CHARS:
            return rendered
        clipped = rendered[:DEFAULT_OUTPUT_MAX_CHARS]
        return f"{clipped}\n... (truncated)"

    def _json_error(self, message: str) -> str:
        return self._json({"ok": False, "error": message})

    async def _action_start(self, task_id: str, *, headed: bool) -> str:
        state = self._get_state(task_id)
        browser_running = self._is_browser_running(state)
        if browser_running and (not headed or not state["headless"]):
            return self._json({"ok": True, "message": "Browser already running"})
        if browser_running and headed and state["headless"]:
            await self._action_stop(task_id)

        state["headless"] = not headed
        if not await self._ensure_browser(task_id):
            return self._json_error(
                f"Browser start failed: {state.get('last_browser_error') or 'unknown error'}"
            )
        message = "Browser started (visible window)" if headed else "Browser started"
        return self._json({"ok": True, "message": message})

    async def _action_stop(self, task_id: str) -> str:
        state = self._get_state(task_id)
        self._cancel_idle_watchdog(state)
        if not self._is_browser_running(state):
            return self._json({"ok": True, "message": "Browser not running"})
        try:
            if _USE_SYNC_PLAYWRIGHT:
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(_get_executor(), lambda: self._sync_browser_close(state))
            else:
                await state["browser"].close()
                if state.get("playwright") is not None:
                    await state["playwright"].stop()
        except Exception as exc:
            return self._json_error(f"Browser stop failed: {exc!s}")
        finally:
            self._reset_browser_state(state)
        return self._json({"ok": True, "message": "Browser stopped"})

    async def _action_open(self, task_id: str, url: str, page_id: str) -> str:
        url = url.strip()
        if not url:
            return self._json_error("url required for open")
        state = self._get_state(task_id)
        if not await self._ensure_browser(task_id):
            return self._json_error(state.get("last_browser_error") or "Browser not started")
        try:
            if _USE_SYNC_PLAYWRIGHT:
                loop = asyncio.get_event_loop()
                page = await loop.run_in_executor(
                    _get_executor(), lambda: state["sync_context"].new_page()
                )
            else:
                page = await state["context"].new_page()

            state["refs"][page_id] = {}
            state["console_logs"][page_id] = []
            state["network_requests"][page_id] = []
            state["pending_dialogs"][page_id] = []
            state["pending_file_choosers"][page_id] = []
            self._attach_page_listeners(state, page_id, page)

            if _USE_SYNC_PLAYWRIGHT:
                await self._run_sync(page.goto, url)
            else:
                await page.goto(url)

            state["pages"][page_id] = page
            state["current_page_id"] = page_id
            self._touch_activity(state)
            return self._json(
                {"ok": True, "message": f"Opened {url}", "page_id": page_id, "url": url}
            )
        except Exception as exc:
            return self._json_error(f"Open failed: {exc!s}")

    async def _action_navigate(self, task_id: str, url: str, page_id: str) -> str:
        url = url.strip()
        if not url:
            return self._json_error("url required for navigate")
        state = self._get_state(task_id)
        page = self._get_page(state, page_id)
        if page is None:
            return self._json_error(f"Page '{page_id}' not found")
        try:
            if _USE_SYNC_PLAYWRIGHT:
                await self._run_sync(page.goto, url)
            else:
                await page.goto(url)
            state["current_page_id"] = page_id
            self._touch_activity(state)
            return self._json({"ok": True, "message": f"Navigated to {url}", "url": page.url})
        except Exception as exc:
            return self._json_error(f"Navigate failed: {exc!s}")

    async def _action_navigate_back(self, task_id: str, page_id: str) -> str:
        state = self._get_state(task_id)
        page = self._get_page(state, page_id)
        if page is None:
            return self._json_error(f"Page '{page_id}' not found")
        try:
            if _USE_SYNC_PLAYWRIGHT:
                await self._run_sync(page.go_back)
            else:
                await page.go_back()
            self._touch_activity(state)
            return self._json({"ok": True, "message": "Navigated back", "url": page.url})
        except Exception as exc:
            return self._json_error(f"Navigate back failed: {exc!s}")

    async def _action_screenshot(
        self,
        task_id: str,
        *,
        page_id: str,
        path: str,
        full_page: bool,
        screenshot_type: str,
        ref: str,
        frame_selector: str,
    ) -> str:
        state = self._get_state(task_id)
        page = self._get_page(state, page_id)
        if page is None:
            return self._json_error(f"Page '{page_id}' not found")
        extension = "jpeg" if screenshot_type == "jpeg" else "png"
        target_path = self._artifact_path(path, f"page-{int(time.time())}.{extension}")
        try:
            if ref.strip():
                locator = self._get_locator_by_ref(
                    state, page, page_id, ref.strip(), frame_selector
                )
                if locator is None:
                    return self._json_error(f"Unknown ref: {ref}")
                await self._run_sync(locator.screenshot, path=str(target_path), type=extension)
            elif frame_selector.strip():
                locator = self._get_root(page, frame_selector).locator("body").first
                await self._run_sync(locator.screenshot, path=str(target_path), type=extension)
            else:
                await self._run_sync(
                    page.screenshot,
                    path=str(target_path),
                    full_page=full_page,
                    type=extension,
                )
            self._touch_activity(state)
            return self._json(
                {
                    "ok": True,
                    "message": f"Screenshot saved to {target_path}",
                    "path": str(target_path),
                }
            )
        except Exception as exc:
            return self._json_error(f"Screenshot failed: {exc!s}")

    async def _action_snapshot(
        self, task_id: str, *, page_id: str, filename: str, frame_selector: str
    ) -> str:
        state = self._get_state(task_id)
        page = self._get_page(state, page_id)
        if page is None:
            return self._json_error(f"Page '{page_id}' not found")
        try:
            root = self._get_root(page, frame_selector)
            locator = root.locator(":root")
            raw = await self._run_sync(locator.aria_snapshot)
            snapshot, refs = build_role_snapshot_from_aria(
                str(raw or ""), interactive=False, compact=False
            )
            state["refs"][page_id] = refs
            state["refs_frame"][page_id] = frame_selector.strip()
            payload: dict[str, Any] = {
                "ok": True,
                "refs": list(refs.keys()),
                "snapshot": snapshot,
                "url": page.url,
            }
            if frame_selector.strip():
                payload["frame_selector"] = frame_selector.strip()
            if filename.strip():
                snapshot_path = self._artifact_path(filename, "snapshot.txt")
                snapshot_path.write_text(snapshot, encoding="utf-8")
                payload["filename"] = str(snapshot_path)
            self._touch_activity(state)
            return self._json(payload)
        except Exception as exc:
            return self._json_error(f"Snapshot failed: {exc!s}")

    async def _action_click(
        self,
        task_id: str,
        *,
        page_id: str,
        selector: str,
        ref: str,
        wait: int,
        double_click: bool,
        button: str,
        modifiers_json: str,
        frame_selector: str,
    ) -> str:
        selector = selector.strip()
        ref = ref.strip()
        if not ref and not selector:
            return self._json_error("selector or ref required for click")
        state = self._get_state(task_id)
        page = self._get_page(state, page_id)
        if page is None:
            return self._json_error(f"Page '{page_id}' not found")
        if wait > 0:
            await asyncio.sleep(wait / 1000.0)
        modifiers = self._parse_json_param(modifiers_json, [])
        if not isinstance(modifiers, list):
            modifiers = []
        kwargs: dict[str, Any] = {
            "button": button if button in {"left", "middle", "right"} else "left"
        }
        filtered_modifiers = [
            modifier
            for modifier in modifiers
            if modifier in {"Alt", "Control", "ControlOrMeta", "Meta", "Shift"}
        ]
        if filtered_modifiers:
            kwargs["modifiers"] = filtered_modifiers
        try:
            if ref:
                locator = self._get_locator_by_ref(state, page, page_id, ref, frame_selector)
                if locator is None:
                    return self._json_error(f"Unknown ref: {ref}")
            else:
                locator = self._get_root(page, frame_selector).locator(selector).first
            if double_click:
                await self._run_sync(locator.dblclick, **kwargs)
            else:
                await self._run_sync(locator.click, **kwargs)
            self._touch_activity(state)
            return self._json({"ok": True, "message": f"Clicked {ref or selector}"})
        except Exception as exc:
            return self._json_error(f"Click failed: {exc!s}")

    async def _action_type(
        self,
        task_id: str,
        *,
        page_id: str,
        selector: str,
        ref: str,
        text: str,
        submit: bool,
        slowly: bool,
        frame_selector: str,
    ) -> str:
        selector = selector.strip()
        ref = ref.strip()
        if not ref and not selector:
            return self._json_error("selector or ref required for type")
        state = self._get_state(task_id)
        page = self._get_page(state, page_id)
        if page is None:
            return self._json_error(f"Page '{page_id}' not found")
        try:
            if ref:
                locator = self._get_locator_by_ref(state, page, page_id, ref, frame_selector)
                if locator is None:
                    return self._json_error(f"Unknown ref: {ref}")
            else:
                locator = self._get_root(page, frame_selector).locator(selector).first
            if slowly:
                await self._run_sync(locator.press_sequentially, text)
            else:
                await self._run_sync(locator.fill, text)
            if submit:
                await self._run_sync(locator.press, "Enter")
            self._touch_activity(state)
            return self._json({"ok": True, "message": f"Typed into {ref or selector}"})
        except Exception as exc:
            return self._json_error(f"Type failed: {exc!s}")

    async def _action_eval(self, task_id: str, page_id: str, code: str) -> str:
        code = code.strip()
        if not code:
            return self._json_error("code required for eval")
        state = self._get_state(task_id)
        page = self._get_page(state, page_id)
        if page is None:
            return self._json_error(f"Page '{page_id}' not found")
        try:
            result = await self._evaluate_code(page, code)
            self._touch_activity(state)
            return self._serialize_result(result)
        except Exception as exc:
            return self._json_error(f"Eval failed: {exc!s}")

    async def _action_evaluate(
        self,
        task_id: str,
        *,
        page_id: str,
        code: str,
        ref: str,
        frame_selector: str,
    ) -> str:
        code = code.strip()
        ref = ref.strip()
        if not code:
            return self._json_error("code required for evaluate")
        state = self._get_state(task_id)
        page = self._get_page(state, page_id)
        if page is None:
            return self._json_error(f"Page '{page_id}' not found")
        try:
            if ref:
                locator = self._get_locator_by_ref(state, page, page_id, ref, frame_selector)
                if locator is None:
                    return self._json_error(f"Unknown ref: {ref}")
                result = await self._run_sync(locator.evaluate, code)
            else:
                result = await self._evaluate_code(page, code)
            self._touch_activity(state)
            return self._serialize_result(result)
        except Exception as exc:
            return self._json_error(f"Evaluate failed: {exc!s}")

    async def _action_resize(self, task_id: str, *, page_id: str, width: int, height: int) -> str:
        if width <= 0 or height <= 0:
            return self._json_error("width and height must be positive")
        state = self._get_state(task_id)
        page = self._get_page(state, page_id)
        if page is None:
            return self._json_error(f"Page '{page_id}' not found")
        try:
            await self._run_sync(page.set_viewport_size, {"width": width, "height": height})
            self._touch_activity(state)
            return self._json({"ok": True, "message": f"Resized to {width}x{height}"})
        except Exception as exc:
            return self._json_error(f"Resize failed: {exc!s}")

    async def _action_console_messages(
        self,
        task_id: str,
        *,
        page_id: str,
        level: str,
        filename: str,
    ) -> str:
        state = self._get_state(task_id)
        page = self._get_page(state, page_id)
        if page is None:
            return self._json_error(f"Page '{page_id}' not found")
        order = ("error", "warning", "info", "debug")
        requested_level = _normalize_console_level(level)
        cutoff = order.index(requested_level) if requested_level in order else order.index("info")
        logs = state["console_logs"].get(page_id, [])
        filtered = [message for message in logs if order.index(message["level"]) <= cutoff]
        text = "\n".join(f"[{message['level']}] {message['text']}" for message in filtered)
        if filename.strip():
            output_path = self._artifact_path(filename, "console.log")
            output_path.write_text(text, encoding="utf-8")
            return self._json(
                {
                    "ok": True,
                    "message": f"Console messages saved to {output_path}",
                    "filename": str(output_path),
                }
            )
        return self._json({"ok": True, "messages": filtered, "text": text})

    async def _action_handle_dialog(
        self,
        task_id: str,
        *,
        page_id: str,
        accept: bool,
        prompt_text: str,
    ) -> str:
        state = self._get_state(task_id)
        page = self._get_page(state, page_id)
        if page is None:
            return self._json_error(f"Page '{page_id}' not found")
        dialogs = state["pending_dialogs"].get(page_id, [])
        if not dialogs:
            return self._json_error("No pending dialog")
        try:
            dialog = dialogs.pop(0)
            if accept:
                if prompt_text:
                    await self._run_sync(dialog.accept, prompt_text)
                else:
                    await self._run_sync(dialog.accept)
            else:
                await self._run_sync(dialog.dismiss)
            self._touch_activity(state)
            return self._json({"ok": True, "message": "Dialog handled"})
        except Exception as exc:
            return self._json_error(f"Handle dialog failed: {exc!s}")

    async def _action_file_upload(self, task_id: str, *, page_id: str, paths_json: str) -> str:
        state = self._get_state(task_id)
        page = self._get_page(state, page_id)
        if page is None:
            return self._json_error(f"Page '{page_id}' not found")
        paths = self._parse_json_param(paths_json, [])
        if not isinstance(paths, list):
            paths = []
        choosers = state["pending_file_choosers"].get(page_id, [])
        if not choosers:
            return self._json_error("No chooser. Click upload then file_upload.")
        try:
            chooser = choosers.pop(0)
            if paths:
                resolved_paths = [
                    str(self._workspace_path(str(path), allow_empty=True)) for path in paths
                ]
                await self._run_sync(chooser.set_files, resolved_paths)
                self._touch_activity(state)
                return self._json(
                    {"ok": True, "message": f"Uploaded {len(resolved_paths)} file(s)"}
                )
            await self._run_sync(chooser.set_files, [])
            self._touch_activity(state)
            return self._json({"ok": True, "message": "File chooser cancelled"})
        except Exception as exc:
            return self._json_error(f"File upload failed: {exc!s}")

    async def _action_fill_form(self, task_id: str, *, page_id: str, fields_json: str) -> str:
        state = self._get_state(task_id)
        page = self._get_page(state, page_id)
        if page is None:
            return self._json_error(f"Page '{page_id}' not found")
        fields = self._parse_json_param(fields_json, [])
        if not isinstance(fields, list) or not fields:
            return self._json_error("fields required (JSON array)")
        refs = self._get_refs(state, page_id)
        frame_selector = state["refs_frame"].get(page_id, "")
        try:
            for field in fields:
                ref = str(field.get("ref", "")).strip()
                if not ref or ref not in refs:
                    continue
                locator = self._get_locator_by_ref(state, page, page_id, ref, frame_selector)
                if locator is None:
                    continue
                field_type = str(field.get("type", "textbox")).lower()
                value = field.get("value")
                if field_type == "checkbox":
                    if isinstance(value, str):
                        value = value.strip().lower() in {"true", "1", "yes"}
                    await self._run_sync(locator.set_checked, bool(value))
                elif field_type == "radio":
                    await self._run_sync(locator.set_checked, True)
                elif field_type == "combobox":
                    await self._run_sync(
                        locator.select_option,
                        label=value if isinstance(value, str) else None,
                        value=value,
                    )
                else:
                    await self._run_sync(locator.fill, "" if value is None else str(value))
            self._touch_activity(state)
            return self._json({"ok": True, "message": f"Filled {len(fields)} field(s)"})
        except Exception as exc:
            return self._json_error(f"Fill form failed: {exc!s}")

    def _run_playwright_install(self) -> None:
        subprocess.run(
            [sys.executable, "-m", "playwright", "install"],
            check=True,
            capture_output=True,
            text=True,
            timeout=600,
        )

    async def _action_install(self) -> str:
        executable_path = self._chromium_executable_path()
        if executable_path:
            return self._json(
                {"ok": True, "message": f"Using system browser (no download): {executable_path}"}
            )
        try:
            await asyncio.to_thread(self._run_playwright_install)
            return self._json({"ok": True, "message": "Browser installed"})
        except subprocess.TimeoutExpired:
            return self._json_error(
                "Browser install timed out (10 min). Run manually: "
                f"{sys.executable} -m playwright install"
            )
        except Exception as exc:
            return self._json_error(
                "Install failed: "
                f"{exc!s}. Install manually with {sys.executable} -m pip install playwright && "
                f"{sys.executable} -m playwright install"
            )

    async def _action_press_key(self, task_id: str, *, page_id: str, key: str) -> str:
        key = key.strip()
        if not key:
            return self._json_error("key required for press_key")
        state = self._get_state(task_id)
        page = self._get_page(state, page_id)
        if page is None:
            return self._json_error(f"Page '{page_id}' not found")
        try:
            await self._run_sync(page.keyboard.press, key)
            self._touch_activity(state)
            return self._json({"ok": True, "message": f"Pressed key {key}"})
        except Exception as exc:
            return self._json_error(f"Press key failed: {exc!s}")

    async def _action_network_requests(
        self,
        task_id: str,
        *,
        page_id: str,
        include_static: bool,
        filename: str,
    ) -> str:
        state = self._get_state(task_id)
        page = self._get_page(state, page_id)
        if page is None:
            return self._json_error(f"Page '{page_id}' not found")
        requests = state["network_requests"].get(page_id, [])
        if not include_static:
            requests = [
                request
                for request in requests
                if request.get("resourceType") not in {"font", "image", "media", "stylesheet"}
            ]
        text = "\n".join(
            f"{request.get('method', '')} {request.get('url', '')} {request.get('status', '')}"
            for request in requests
        )
        if filename.strip():
            output_path = self._artifact_path(filename, "network.log")
            output_path.write_text(text, encoding="utf-8")
            return self._json(
                {
                    "ok": True,
                    "message": f"Network requests saved to {output_path}",
                    "filename": str(output_path),
                }
            )
        return self._json({"ok": True, "requests": requests, "text": text})

    async def _action_run_code(self, task_id: str, page_id: str, code: str) -> str:
        return await self._action_eval(task_id, page_id, code)

    async def _action_drag(
        self,
        task_id: str,
        *,
        page_id: str,
        start_ref: str,
        end_ref: str,
        start_selector: str,
        end_selector: str,
        frame_selector: str,
    ) -> str:
        start_ref = start_ref.strip()
        end_ref = end_ref.strip()
        start_selector = start_selector.strip()
        end_selector = end_selector.strip()
        use_refs = bool(start_ref and end_ref)
        use_selectors = bool(start_selector and end_selector)
        if not use_refs and not use_selectors:
            return self._json_error(
                "drag needs (start_ref,end_ref) or (start_selector,end_selector)"
            )
        state = self._get_state(task_id)
        page = self._get_page(state, page_id)
        if page is None:
            return self._json_error(f"Page '{page_id}' not found")
        try:
            root = self._get_root(page, frame_selector)
            if use_refs:
                start_locator = self._get_locator_by_ref(
                    state, page, page_id, start_ref, frame_selector
                )
                end_locator = self._get_locator_by_ref(
                    state, page, page_id, end_ref, frame_selector
                )
                if start_locator is None or end_locator is None:
                    return self._json_error("Unknown ref for drag")
            else:
                start_locator = root.locator(start_selector).first
                end_locator = root.locator(end_selector).first
            await self._run_sync(start_locator.drag_to, end_locator)
            self._touch_activity(state)
            return self._json({"ok": True, "message": "Drag completed"})
        except Exception as exc:
            return self._json_error(f"Drag failed: {exc!s}")

    async def _action_hover(
        self,
        task_id: str,
        *,
        page_id: str,
        ref: str,
        selector: str,
        frame_selector: str,
    ) -> str:
        ref = ref.strip()
        selector = selector.strip()
        if not ref and not selector:
            return self._json_error("hover requires ref or selector")
        state = self._get_state(task_id)
        page = self._get_page(state, page_id)
        if page is None:
            return self._json_error(f"Page '{page_id}' not found")
        try:
            if ref:
                locator = self._get_locator_by_ref(state, page, page_id, ref, frame_selector)
                if locator is None:
                    return self._json_error(f"Unknown ref: {ref}")
            else:
                locator = self._get_root(page, frame_selector).locator(selector).first
            await self._run_sync(locator.hover)
            self._touch_activity(state)
            return self._json({"ok": True, "message": f"Hovered {ref or selector}"})
        except Exception as exc:
            return self._json_error(f"Hover failed: {exc!s}")

    async def _action_select_option(
        self,
        task_id: str,
        *,
        page_id: str,
        ref: str,
        values_json: str,
        frame_selector: str,
    ) -> str:
        ref = ref.strip()
        if not ref:
            return self._json_error("ref required for select_option")
        values = self._parse_json_param(values_json, [])
        if not isinstance(values, list):
            values = [values] if values is not None else []
        if not values:
            return self._json_error("values required (JSON array or comma-separated)")
        state = self._get_state(task_id)
        page = self._get_page(state, page_id)
        if page is None:
            return self._json_error(f"Page '{page_id}' not found")
        locator = self._get_locator_by_ref(state, page, page_id, ref, frame_selector)
        if locator is None:
            return self._json_error(f"Unknown ref: {ref}")
        try:
            await self._run_sync(locator.select_option, value=values)
            self._touch_activity(state)
            return self._json({"ok": True, "message": f"Selected {values}"})
        except Exception as exc:
            return self._json_error(f"Select option failed: {exc!s}")

    async def _action_tabs(self, task_id: str, *, page_id: str, tab_action: str, index: int) -> str:
        tab_action = tab_action.strip().lower()
        if not tab_action:
            return self._json_error("tab_action required (list, new, close, select)")
        state = self._get_state(task_id)
        page_ids = list(state["pages"].keys())
        if tab_action == "list":
            return self._json({"ok": True, "tabs": page_ids, "count": len(page_ids)})
        if tab_action == "new":
            if not await self._ensure_browser(task_id):
                return self._json_error(state.get("last_browser_error") or "Browser not started")
            try:
                if _USE_SYNC_PLAYWRIGHT:
                    page = await self._run_sync(state["sync_context"].new_page)
                else:
                    page = await state["context"].new_page()
                new_page_id = self._next_page_id(state)
                state["refs"][new_page_id] = {}
                state["console_logs"][new_page_id] = []
                state["network_requests"][new_page_id] = []
                state["pending_dialogs"][new_page_id] = []
                state["pending_file_choosers"][new_page_id] = []
                self._attach_page_listeners(state, new_page_id, page)
                state["pages"][new_page_id] = page
                state["current_page_id"] = new_page_id
                self._touch_activity(state)
                return self._json(
                    {"ok": True, "page_id": new_page_id, "tabs": list(state["pages"].keys())}
                )
            except Exception as exc:
                return self._json_error(f"New tab failed: {exc!s}")
        if tab_action == "close":
            target_id = page_ids[index] if 0 <= index < len(page_ids) else page_id
            return await self._action_close(task_id, target_id)
        if tab_action == "select":
            target_id = page_ids[index] if 0 <= index < len(page_ids) else page_id
            if target_id not in state["pages"]:
                return self._json_error(f"Page '{target_id}' not found")
            state["current_page_id"] = target_id
            return self._json(
                {
                    "ok": True,
                    "message": f"Use page_id={target_id} for later actions",
                    "page_id": target_id,
                }
            )
        return self._json_error(f"Unknown tab_action: {tab_action}")

    async def _action_wait_for(
        self,
        task_id: str,
        *,
        page_id: str,
        wait_time: float,
        text: str,
        text_gone: str,
    ) -> str:
        state = self._get_state(task_id)
        page = self._get_page(state, page_id)
        if page is None:
            return self._json_error(f"Page '{page_id}' not found")
        try:
            if wait_time > 0:
                await asyncio.sleep(wait_time)
            if text.strip():
                await self._run_sync(
                    page.get_by_text(text.strip()).wait_for, state="visible", timeout=30_000
                )
            if text_gone.strip():
                await self._run_sync(
                    page.get_by_text(text_gone.strip()).wait_for, state="hidden", timeout=30_000
                )
            self._touch_activity(state)
            return self._json({"ok": True, "message": "Wait completed"})
        except Exception as exc:
            return self._json_error(f"Wait failed: {exc!s}")

    async def _action_pdf(self, task_id: str, *, page_id: str, path: str) -> str:
        state = self._get_state(task_id)
        page = self._get_page(state, page_id)
        if page is None:
            return self._json_error(f"Page '{page_id}' not found")
        target_path = self._artifact_path(path, "page.pdf")
        try:
            await self._run_sync(page.pdf, path=str(target_path))
            self._touch_activity(state)
            return self._json(
                {"ok": True, "message": f"PDF saved to {target_path}", "path": str(target_path)}
            )
        except Exception as exc:
            return self._json_error(f"PDF failed: {exc!s}")

    async def _action_close(self, task_id: str, page_id: str) -> str:
        state = self._get_state(task_id)
        page = self._get_page(state, page_id)
        if page is None:
            return self._json_error(f"Page '{page_id}' not found")
        try:
            await self._run_sync(page.close)
            del state["pages"][page_id]
            for key in (
                "refs",
                "refs_frame",
                "console_logs",
                "network_requests",
                "pending_dialogs",
                "pending_file_choosers",
            ):
                state[key].pop(page_id, None)
            if state.get("current_page_id") == page_id:
                remaining = list(state["pages"].keys())
                state["current_page_id"] = remaining[0] if remaining else None
            self._touch_activity(state)
            return self._json({"ok": True, "message": f"Closed page '{page_id}'"})
        except Exception as exc:
            return self._json_error(f"Close failed: {exc!s}")

    async def _evaluate_code(self, page: Any, code: str) -> Any:
        code = code.strip()
        expression = (
            code
            if code.startswith("(") or code.startswith("function")
            else f"() => {{ return ({code}); }}"
        )
        return await self._run_sync(page.evaluate, expression)

    def _serialize_result(self, result: Any) -> str:
        try:
            return self._json({"ok": True, "result": result})
        except TypeError:
            return self._json({"ok": True, "result": str(result)})
