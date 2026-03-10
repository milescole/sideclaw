"""Tool for scheduling recurring agent tasks."""

from contextvars import ContextVar, Token
from datetime import datetime
from typing import Any

from sideclaw.cron import CronService
from sideclaw.runtime.context import get_tool_runtime_context
from sideclaw.tools.base import Tool


class CronTool(Tool):
    """Schedule recurring prompts for the current conversation context."""

    def __init__(self, cron_service: CronService) -> None:
        self._cron = cron_service
        self._in_cron_context: ContextVar[bool] = ContextVar("cron_in_context", default=False)

    def set_cron_context(self, active: bool) -> Token[bool]:
        """Mark whether the tool is executing inside a cron job callback."""
        return self._in_cron_context.set(active)

    def reset_cron_context(self, token: Token[bool]) -> None:
        """Restore the previous cron execution marker."""
        self._in_cron_context.reset(token)

    @property
    def name(self) -> str:
        return "cron"

    @property
    def description(self) -> str:
        return "Schedule recurring or one-time prompts for the current chat"

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["add", "list", "remove", "enable", "disable"],
                    "description": "Action to perform",
                },
                "prompt": {
                    "type": "string",
                    "description": "Prompt to run when the scheduled job fires",
                },
                "schedule": {
                    "type": "string",
                    "description": "Cron expression like '0 21 * * 5'",
                },
                "job_id": {
                    "type": "string",
                    "description": "Cron job ID for remove/enable/disable",
                },
                "name": {
                    "type": "string",
                    "description": "Optional human-readable job name",
                },
            },
            "required": ["action"],
        }

    async def execute(
        self,
        *,
        action: str,
        prompt: str | None = None,
        schedule: str | None = None,
        job_id: str | None = None,
        name: str | None = None,
        **_: Any,
    ) -> str:
        if action == "add":
            return self._add_job(prompt=prompt, schedule=schedule, name=name)
        if action == "list":
            return self._list_jobs()
        if action == "remove":
            return self._remove_job(job_id)
        if action == "enable":
            return self._set_enabled(job_id, True)
        if action == "disable":
            return self._set_enabled(job_id, False)
        return f"Error: Unknown action '{action}'"

    def _add_job(
        self,
        *,
        prompt: str | None,
        schedule: str | None,
        name: str | None,
    ) -> str:
        if self._in_cron_context.get():
            return "Error: cannot schedule new jobs from within a cron job execution"
        if not prompt or not prompt.strip():
            return "Error: prompt is required for add"
        if not schedule or not schedule.strip():
            return "Error: schedule is required for add"

        context = get_tool_runtime_context()
        if context is None:
            return "Error: no active runtime context for cron scheduling"

        try:
            job = self._cron.add_job(
                schedule=schedule.strip(),
                prompt=prompt.strip(),
                channel=context.channel,
                chat_id=context.chat_id,
                name=name.strip() if name else None,
            )
        except ValueError as exc:
            return f"Error: {exc}"

        label = job.name or job.prompt[:40]
        return (
            f"Created cron job '{label}' (id: {job.job_id}) "
            f"for {job.channel}:{job.chat_id} on schedule '{job.schedule}'."
        )

    def _list_jobs(self) -> str:
        context = get_tool_runtime_context()
        jobs = self._cron.list_jobs()
        if context is not None:
            jobs = [
                job
                for job in jobs
                if job.channel == context.channel and job.chat_id == context.chat_id
            ]
        if not jobs:
            return "No scheduled jobs."

        lines = []
        for job in jobs:
            next_run = self._cron.next_run_at(job)
            next_run_text = next_run.isoformat() if next_run is not None else "disabled"
            label = job.name or job.prompt[:40]
            lines.append(
                f"- {label} (id: {job.job_id}, schedule: {job.schedule}, next: {next_run_text})"
            )
        return "Scheduled jobs:\n" + "\n".join(lines)

    def _remove_job(self, job_id: str | None) -> str:
        if not job_id:
            return "Error: job_id is required for remove"
        if self._cron.remove_job(job_id):
            return f"Removed cron job {job_id}"
        return f"Error: cron job not found: {job_id}"

    def _set_enabled(self, job_id: str | None, enabled: bool) -> str:
        if not job_id:
            return "Error: job_id is required"
        if self._cron.set_enabled(job_id, enabled):
            state = "enabled" if enabled else "disabled"
            return f"{state.capitalize()} cron job {job_id}"
        return f"Error: cron job not found: {job_id}"
