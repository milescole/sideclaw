from pathlib import Path

from sideclaw.utils.files import atomic_append_text, atomic_write_text


def test_atomic_write_text_writes_content(tmp_path: Path) -> None:
    target = tmp_path / "nested" / "file.txt"

    atomic_write_text(target, "hello")

    assert target.read_text() == "hello"


def test_atomic_write_text_cleans_up_temp_file(tmp_path: Path) -> None:
    target = tmp_path / "file.txt"

    atomic_write_text(target, "hello")

    leftovers = list(tmp_path.glob(".file.txt.*.tmp"))
    assert leftovers == []


def test_atomic_append_text_preserves_existing_content(tmp_path: Path) -> None:
    target = tmp_path / "log.txt"
    target.write_text("first\n")

    atomic_append_text(target, "second\n")

    assert target.read_text() == "first\nsecond\n"
