from pathlib import Path

from sideclaw.cron.history import CronHistory, CronHistoryEntry


def test_record_and_retrieve(tmp_path: Path) -> None:
    history = CronHistory(tmp_path / "history.jsonl")
    entry = CronHistoryEntry(
        job_id="job1",
        job_name="test-job",
        started_at="2026-03-21T09:00:00+00:00",
        completed_at="2026-03-21T09:00:01+00:00",
        status="completed",
        duration_ms=1000,
    )
    history.record(entry)

    entries = history.get_entries()
    assert len(entries) == 1
    assert entries[0].job_id == "job1"
    assert entries[0].job_name == "test-job"
    assert entries[0].status == "completed"
    assert entries[0].duration_ms == 1000


def test_filter_by_job_id(tmp_path: Path) -> None:
    history = CronHistory(tmp_path / "history.jsonl")
    history.record(CronHistoryEntry(job_id="job1", job_name="a"))
    history.record(CronHistoryEntry(job_id="job2", job_name="b"))
    history.record(CronHistoryEntry(job_id="job1", job_name="a"))

    entries = history.get_entries(job_id="job1")
    assert len(entries) == 2
    assert all(e.job_id == "job1" for e in entries)


def test_limit_entries(tmp_path: Path) -> None:
    history = CronHistory(tmp_path / "history.jsonl")
    for i in range(10):
        history.record(CronHistoryEntry(job_id=f"job{i}", job_name=f"j{i}"))

    entries = history.get_entries(limit=3)
    assert len(entries) == 3
    # Most recent first
    assert entries[0].job_id == "job9"
