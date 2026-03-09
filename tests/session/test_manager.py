import pytest

from sideclaw.session.manager import SessionManager


@pytest.fixture
def session_dir(tmp_path):
    return tmp_path / "sessions"


@pytest.fixture
def manager(session_dir):
    return SessionManager(session_dir)


def test_get_or_create_new_session(manager):
    session = manager.get_or_create("cli:user1")
    assert session.key == "cli:user1"
    assert session.messages == []
    assert session.last_consolidated == 0


def test_get_or_create_returns_same_session(manager):
    s1 = manager.get_or_create("cli:user1")
    s1.messages.append({"role": "user", "content": "hello"})
    s2 = manager.get_or_create("cli:user1")
    assert s2.messages == [{"role": "user", "content": "hello"}]


def test_save_and_reload(session_dir):
    m1 = SessionManager(session_dir)
    s = m1.get_or_create("telegram:123")
    s.messages.append({"role": "user", "content": "hi"})
    s.messages.append({"role": "assistant", "content": "hello!"})
    m1.save(s)

    m2 = SessionManager(session_dir)
    s2 = m2.get_or_create("telegram:123")
    assert len(s2.messages) == 2
    assert s2.messages[0]["content"] == "hi"
    assert s2.messages[1]["content"] == "hello!"


def test_get_history_limits_messages(manager):
    s = manager.get_or_create("cli:user1")
    for i in range(10):
        s.messages.append({"role": "user", "content": f"msg {i}"})
    history = s.get_history(max_messages=3)
    assert len(history) == 3
    assert history[0]["content"] == "msg 7"


def test_get_history_aligns_to_user_turn(manager):
    s = manager.get_or_create("cli:user1")
    s.messages.append({"role": "assistant", "content": "leftover"})
    s.messages.append({"role": "user", "content": "hello"})
    s.messages.append({"role": "assistant", "content": "hi"})
    history = s.get_history(max_messages=10)
    assert history[0]["role"] == "user"


def test_session_clear(manager):
    s = manager.get_or_create("cli:user1")
    s.messages.append({"role": "user", "content": "hi"})
    s.clear()
    assert s.messages == []
    assert s.last_consolidated == 0


def test_list_sessions(manager):
    manager.get_or_create("cli:user1")
    manager.save(manager.get_or_create("cli:user1"))
    manager.get_or_create("telegram:123")
    manager.save(manager.get_or_create("telegram:123"))
    sessions = manager.list_sessions()
    assert len(sessions) == 2


def test_get_history_respects_last_consolidated(manager):
    s = manager.get_or_create("cli:user1")
    for i in range(10):
        s.messages.append({"role": "user", "content": f"msg {i}"})
    s.last_consolidated = 6
    history = s.get_history(max_messages=100)
    assert len(history) == 4
    assert history[0]["content"] == "msg 6"


def test_get_or_create_quarantines_unreadable_session_file(session_dir):
    broken_path = session_dir / "cli__user1.jsonl"
    session_dir.mkdir(parents=True, exist_ok=True)
    broken_path.write_text("{not json")

    manager = SessionManager(session_dir)
    session = manager.get_or_create("cli:user1")

    assert session.key == "cli:user1"
    assert session.messages == []
    assert broken_path.exists() is False

    quarantined = list((session_dir / "quarantine").glob("cli__user1-*.jsonl"))
    assert len(quarantined) == 1
    assert quarantined[0].read_text() == "{not json"


def test_get_or_create_quarantines_partial_corruption_and_salvages_messages(session_dir):
    session_dir.mkdir(parents=True, exist_ok=True)
    broken_path = session_dir / "telegram__123.jsonl"
    broken_path.write_text(
        '{"_type":"metadata","created_at":"2026-03-08T00:00:00+00:00","updated_at":"2026-03-08T00:00:00+00:00","last_consolidated":0}\n'
        '{"role":"user","content":"hello"}\n'
        "{broken\n"
        '{"role":"assistant","content":"world"}\n'
    )

    manager = SessionManager(session_dir)
    session = manager.get_or_create("telegram:123")

    assert [msg["content"] for msg in session.messages] == ["hello", "world"]
    assert broken_path.exists() is False

    quarantined = list((session_dir / "quarantine").glob("telegram__123-*.jsonl"))
    assert len(quarantined) == 1
