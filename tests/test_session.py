from olinkb.session import SessionManager


def test_session_manager_tracks_reads_and_writes() -> None:
    manager = SessionManager()

    session = manager.start(session_id="session-1", author="rzjulio", project="olinkb")
    manager.bump_reads("session-1", count=2)
    manager.bump_writes("session-1", count=1)
    finished = manager.end("session-1")

    assert session.session_id == "session-1"
    assert finished.memories_read == 2
    assert finished.memories_written == 1
    assert finished.project == "olinkb"