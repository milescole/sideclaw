import pytest

from sideclaw.session.manager import SessionManager


@pytest.fixture
def session_dir(tmp_path):
    return tmp_path / "sessions"


@pytest.fixture
def manager(session_dir):
    return SessionManager(session_dir)


def test_list_sessions_includes_title_and_message_count(manager):
    session = manager.get_or_create("cli:user1")
    session.title = "Python Help"
    session.messages = [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "hi there"},
    ]
    manager.save(session)

    sessions = manager.list_sessions()

    assert len(sessions) == 1
    entry = sessions[0]
    assert entry["key"] == "cli:user1"
    assert entry["title"] == "Python Help"
    assert entry["message_count"] == 2


def test_list_sessions_shows_none_title_for_untitled(manager):
    session = manager.get_or_create("cli:user1")
    manager.save(session)

    sessions = manager.list_sessions()

    assert len(sessions) == 1
    assert sessions[0]["title"] is None


def test_delete_session_removes_file(manager, session_dir):
    session = manager.get_or_create("cli:user1")
    manager.save(session)
    assert (session_dir / "cli__user1.jsonl").exists()

    deleted = manager.delete("cli:user1")

    assert deleted is True
    assert not (session_dir / "cli__user1.jsonl").exists()


def test_delete_nonexistent_session_returns_false(manager):
    deleted = manager.delete("cli:nonexistent")
    assert deleted is False


def test_delete_clears_cache(manager):
    session = manager.get_or_create("cli:user1")
    session.messages.append({"role": "user", "content": "hello"})
    manager.save(session)

    manager.delete("cli:user1")

    new_session = manager.get_or_create("cli:user1")
    assert new_session.messages == []


def test_exists_returns_true_for_saved_session(manager):
    session = manager.get_or_create("cli:user1")
    manager.save(session)

    assert manager.exists("cli:user1") is True


def test_exists_returns_false_for_missing_session(manager):
    assert manager.exists("cli:nonexistent") is False


def test_rename_sets_user_title(manager):
    session = manager.get_or_create("cli:user1")
    manager.save(session)

    result = manager.rename("cli:user1", "My Custom Name")

    assert result is True
    manager.invalidate("cli:user1")
    reloaded = manager.get_or_create("cli:user1")
    assert reloaded.title == "My Custom Name"
    assert reloaded.title_source == "user"


def test_rename_nonexistent_returns_false(manager):
    assert manager.rename("cli:nonexistent", "title") is False


def test_get_session_info_returns_metadata(manager):
    session = manager.get_or_create("cli:user1")
    session.title = "Debug Session"
    session.messages = [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "hi"},
        {"role": "user", "content": "help"},
    ]
    manager.save(session)

    info = manager.get_session_info("cli:user1")

    assert info is not None
    assert info["key"] == "cli:user1"
    assert info["title"] == "Debug Session"
    assert info["message_count"] == 3
    assert "created_at" in info
    assert "updated_at" in info
    assert "last_consolidated" in info


def test_get_session_info_returns_none_for_missing(manager):
    assert manager.get_session_info("cli:nonexistent") is None
