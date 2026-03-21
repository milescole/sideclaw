"""Cron scheduling support."""

from pathlib import Path

from sideclaw.cron.service import CronJob, CronService, _interval_to_cron


def cron_store_path(workspace: Path) -> Path:
    """Return the persisted cron job store path for a workspace."""
    return workspace / "cron" / "jobs.json"


__all__ = ["CronJob", "CronService", "_interval_to_cron", "cron_store_path"]
