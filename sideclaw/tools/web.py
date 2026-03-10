"""Web tools: search and fetch."""

import asyncio
import html
import json
import os
import re
from typing import Any
from urllib.parse import urlparse

import httpx
from loguru import logger

from sideclaw.config.schema import WebSearchProvider
from sideclaw.tools.base import Tool

USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_7_2) AppleWebKit/537.36"
MAX_REDIRECTS = 5
BRAVE_SEARCH_ENDPOINT = "https://api.search.brave.com/res/v1/web/search"
MAX_SEARCH_RESULTS = 20
DEFAULT_SEARCH_RESULTS = 5
MAX_BRAVE_RETRIES = 3


def _strip_tags(text: str) -> str:
    """Remove HTML tags and decode entities."""
    text = re.sub(r"<script[\s\S]*?</script>", "", text, flags=re.IGNORECASE)
    text = re.sub(r"<style[\s\S]*?</style>", "", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    return html.unescape(text).strip()


def _normalize(text: str) -> str:
    """Normalize whitespace."""
    text = re.sub(r"[ \t]+", " ", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _validate_url(url: str) -> tuple[bool, str]:
    """Validate URL: must be http(s) with valid domain."""
    try:
        parsed = urlparse(url)
    except ValueError as exc:
        return False, str(exc)

    if parsed.scheme not in {"http", "https"}:
        return False, f"Only http/https allowed, got '{parsed.scheme or 'none'}'"
    if not parsed.netloc:
        return False, "Missing domain"
    return True, ""


def _extract_hostname(url: str) -> str | None:
    """Extract hostname from an HTTP(S) URL."""
    parsed = urlparse(url)
    return parsed.hostname


def _is_valid_lang_code(value: str) -> bool:
    """Validate a two-letter lowercase language code."""
    return len(value) == 2 and value.isascii() and value.islower() and value.isalpha()


def _is_valid_country_code(value: str) -> bool:
    """Validate a two-letter uppercase country code."""
    return len(value) == 2 and value.isascii() and value.isupper() and value.isalpha()


def _is_valid_ui_lang(value: str) -> bool:
    """Validate a locale like en-US."""
    lang, sep, country = value.partition("-")
    return bool(sep) and _is_valid_lang_code(lang) and _is_valid_country_code(country)


def _is_date_like(value: str) -> bool:
    """Check a YYYY-MM-DD date-like string."""
    return bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", value))


def _is_valid_date_range(value: str) -> bool:
    """Check a Brave-style date range."""
    start, sep, end = value.partition("to")
    return bool(sep) and _is_date_like(start) and _is_date_like(end)


def _is_valid_freshness(value: str) -> bool:
    """Validate a Brave freshness filter."""
    return value in {"pd", "pw", "pm", "py"} or _is_valid_date_range(value)


def _html_to_markdown(raw_html: str) -> str:
    """Convert a small HTML fragment to lightweight markdown."""
    text = re.sub(
        r'<a\s+[^>]*href=["\']([^"\']+)["\'][^>]*>([\s\S]*?)</a>',
        lambda match: f"[{_strip_tags(match[2])}]({match[1]})",
        raw_html,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r"<h([1-6])[^>]*>([\s\S]*?)</h\1>",
        lambda match: f'\n{"#" * int(match[1])} {_strip_tags(match[2])}\n',
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r"<li[^>]*>([\s\S]*?)</li>",
        lambda match: f"\n- {_strip_tags(match[1])}",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r"</(p|div|section|article|main|aside|header|footer)>",
        "\n\n",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(r"<(br|hr)\s*/?>", "\n", text, flags=re.IGNORECASE)
    return _normalize(_strip_tags(text))


def _extract_html_content(document_html: str, *, extract_mode: str) -> tuple[str, str]:
    """Extract readable content from HTML, preferring readability when available."""
    try:
        from readability import Document  # type: ignore[import-not-found]
    except ImportError:
        content = _html_to_markdown(document_html) if extract_mode == "markdown" else _normalize(
            _strip_tags(document_html)
        )
        return content, "fallback"

    doc = Document(document_html)
    summary = doc.summary()
    if extract_mode == "markdown":
        content = _html_to_markdown(summary)
    else:
        content = _normalize(_strip_tags(summary))
    if title := _normalize(doc.title() or ""):
        return f"# {title}\n\n{content}", "readability"
    return content, "readability"


class WebSearchTool(Tool):
    """Search the web using Brave Search API."""

    def __init__(
        self,
        *,
        provider: WebSearchProvider,
        api_key: str | None,
        max_results: int = 5,
    ) -> None:
        self._provider = provider
        self._api_key = api_key
        self._max_results = max_results

    @property
    def name(self) -> str:
        return "web_search"

    @property
    def description(self) -> str:
        return "Search the web and return results"

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
                "count": {
                    "type": "integer",
                    "description": "Number of results to return (1-20)",
                    "minimum": 1,
                    "maximum": 20,
                },
                "country": {
                    "type": "string",
                    "description": "2-letter uppercase country code like US or DE",
                },
                "search_lang": {
                    "type": "string",
                    "description": "2-letter lowercase language code like en or de",
                },
                "ui_lang": {
                    "type": "string",
                    "description": "Locale like en-US or de-DE",
                },
                "freshness": {
                    "type": "string",
                    "description": "pd, pw, pm, py, or YYYY-MM-DDtoYYYY-MM-DD",
                },
            },
            "required": ["query"],
        }

    @staticmethod
    def _validate_search_inputs(
        *,
        query: str,
        filters: dict[str, str | None],
    ) -> str | None:
        """Validate Brave search inputs and return an error string when invalid."""
        error: str | None = None
        if not query:
            error = "Error: 'query' must not be empty"
        elif len(query) > 2000:
            error = "Error: 'query' exceeds maximum length of 2000 characters"
        elif (
            filters["country"] is not None
            and not _is_valid_country_code(str(filters["country"]))
        ):
            country = str(filters["country"])
            error = f"Error: Invalid 'country': expected 2-letter code like 'US', got '{country}'"
        elif (
            filters["search_lang"] is not None
            and not _is_valid_lang_code(str(filters["search_lang"]))
        ):
            search_lang = str(filters["search_lang"])
            error = (
                f"Error: Invalid 'search_lang': expected 2-letter code like 'en', "
                f"got '{search_lang}'"
            )
        elif filters["ui_lang"] is not None and not _is_valid_ui_lang(str(filters["ui_lang"])):
            ui_lang = str(filters["ui_lang"])
            error = f"Error: Invalid 'ui_lang': expected format like 'en-US', got '{ui_lang}'"
        elif (
            filters["freshness"] is not None
            and not _is_valid_freshness(str(filters["freshness"]))
        ):
            freshness = str(filters["freshness"])
            error = (
                "Error: Invalid 'freshness': expected 'pd', 'pw', 'pm', 'py', or "
                f"'YYYY-MM-DDtoYYYY-MM-DD', got '{freshness}'"
            )
        return error

    def _build_search_params(
        self,
        *,
        query: str,
        count: int | None,
        filters: dict[str, str | None],
    ) -> dict[str, str | int]:
        """Build Brave request params."""
        result_count = min(
            max(int(count or self._max_results or DEFAULT_SEARCH_RESULTS), 1),
            MAX_SEARCH_RESULTS,
        )
        params: dict[str, str | int] = {"q": query, "count": result_count}
        params.update({key: value for key, value in filters.items() if value is not None})
        return params

    @staticmethod
    async def _request_results(
        *,
        client: httpx.AsyncClient,
        api_key: str,
        params: dict[str, str | int],
    ) -> list[dict[str, Any]]:
        """Call Brave with retries and return raw result items."""
        response = None
        for attempt in range(1, MAX_BRAVE_RETRIES + 1):
            response = await client.get(
                BRAVE_SEARCH_ENDPOINT,
                params=params,
                headers={"X-Subscription-Token": api_key, "Accept": "application/json"},
                timeout=15,
            )
            if 200 <= response.status_code < 300:
                break
            if attempt < MAX_BRAVE_RETRIES and (
                response.status_code == 429 or response.status_code >= 500
            ):
                logger.warning(
                    "Brave API error {} (attempt {}/{}). Retrying...",
                    response.status_code,
                    attempt,
                    MAX_BRAVE_RETRIES,
                )
                await asyncio.sleep(0.2 * attempt)
                continue
            response.raise_for_status()

        assert response is not None
        return response.json().get("web", {}).get("results", [])

    @staticmethod
    def _format_results(*, query: str, results: list[dict[str, Any]], count: int) -> str:
        """Format Brave results into a readable text block."""
        if not results:
            return f"No results for: {query}"

        lines = [f"Results for: {query}\n"]
        for idx, result in enumerate(results[:count], start=1):
            lines.append(f"{idx}. {result.get('title', '')}\n   {result.get('url', '')}")
            if description := result.get("description"):
                lines.append(f"   {description}")
            if published := result.get("age"):
                lines.append(f"   Published: {published}")
            if site_name := _extract_hostname(result.get("url", "")):
                lines.append(f"   Site: {site_name}")
        return "\n".join(lines)

    async def execute(self, **kwargs) -> str:
        query = kwargs["query"].strip()
        if self._provider is not WebSearchProvider.brave:
            return f"Error: Unsupported web search provider '{self._provider}'"
        api_key = self._api_key or os.environ.get("BRAVE_API_KEY")
        if not api_key:
            return "Error: Brave Search API key not configured."

        country = kwargs.get("country")
        search_lang = kwargs.get("search_lang")
        ui_lang = kwargs.get("ui_lang")
        freshness = kwargs.get("freshness")
        filters = {
            "country": country,
            "search_lang": search_lang,
            "ui_lang": ui_lang,
            "freshness": freshness,
        }
        if error := self._validate_search_inputs(
            query=query,
            filters=filters,
        ):
            return error

        params = self._build_search_params(
            query=query,
            count=kwargs.get("count"),
            filters=filters,
        )
        result_count = int(params["count"])

        try:
            async with httpx.AsyncClient() as client:
                results = await self._request_results(client=client, api_key=api_key, params=params)
            return self._format_results(query=query, results=results, count=result_count)
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as e:
            logger.error("WebSearch error: {}", e)
            return f"Error: {e}"


class WebFetchTool(Tool):
    """Fetch content from a URL."""

    def __init__(
        self,
        *,
        max_chars: int = 50_000,
    ) -> None:
        self._max_chars = max_chars

    @property
    def name(self) -> str:
        return "web_fetch"

    @property
    def description(self) -> str:
        return "Fetch a URL and extract readable content as markdown or plain text"

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "URL to fetch"},
                "extract_mode": {
                    "type": "string",
                    "enum": ["markdown", "text"],
                    "description": "Preferred extraction format",
                    "default": "markdown",
                },
                "max_chars": {
                    "type": "integer",
                    "description": "Maximum characters to return",
                    "minimum": 100,
                },
            },
            "required": ["url"],
        }

    async def execute(self, **kwargs) -> str:
        url = kwargs["url"]
        extract_mode = kwargs.get("extract_mode") or kwargs.get("extractMode") or "markdown"
        max_chars = kwargs.get("max_chars") or kwargs.get("maxChars") or self._max_chars
        is_valid, error_msg = _validate_url(url)
        if not is_valid:
            return json.dumps(
                {
                    "success": False,
                    "error": f"URL validation failed: {error_msg}",
                    "url": url,
                }
            )

        try:
            async with httpx.AsyncClient(
                follow_redirects=True,
                max_redirects=MAX_REDIRECTS,
                timeout=30,
            ) as client:
                resp = await client.get(url, headers={"User-Agent": USER_AGENT})
                resp.raise_for_status()
            content_type = resp.headers.get("content-type", "").lower()

            if "application/json" in content_type:
                text = json.dumps(resp.json(), indent=2, ensure_ascii=False)
                extractor = "json"
            elif "text/html" in content_type or resp.text[:256].lower().startswith(
                ("<!doctype", "<html")
            ):
                text, extractor = _extract_html_content(resp.text, extract_mode=extract_mode)
            else:
                text = resp.text
                extractor = "raw"

            truncated = len(text) > int(max_chars)
            if truncated:
                text = text[: int(max_chars)]

            return json.dumps(
                {
                    "success": True,
                    "url": url,
                    "final_url": str(resp.url),
                    "status": resp.status_code,
                    "extractor": extractor,
                    "truncated": truncated,
                    "length": len(text),
                    "text": text,
                },
                ensure_ascii=False,
            )
        except (httpx.HTTPError, TypeError, ValueError) as e:
            logger.error("WebFetch error for {}: {}", url, e)
            return json.dumps({"success": False, "error": str(e), "url": url}, ensure_ascii=False)
