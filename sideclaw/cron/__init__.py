"""Cron scheduling support."""

from pathlib import Path

from sideclaw.cron.history import CronHistory
from sideclaw.cron.service import CronJob, CronService


def cron_store_path(workspace: Path) -> Path:
    """Return the persisted cron job store path for a workspace."""
    return workspace / "cron" / "jobs.json"


__all__ = ["CronHistory", "CronJob", "CronService", "cron_store_path"]
