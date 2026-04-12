import pytest

from olinkb import viewer_server


class FakeViewerStorage:
    pending_limits: list[int] = []

    def __init__(self, *_args, **_kwargs) -> None:
        self.closed = False

    async def connect(self) -> None:
        return None

    async def close(self) -> None:
        self.closed = True

    async def search_viewer_memories(self, **_kwargs):
        return {
            "memories": [
                {
                    "id": "m1",
                    "uri": "project://olinkb/decisions/viewer",
                    "title": "Viewer decision",
                    "content": "What: Render the live viewer",
                    "memory_type": "decision",
                    "scope": "project",
                    "namespace": "project://olinkb",
                    "author_username": "rzjulio",
                    "tags": ["viewer"],
                    "metadata": {"what": "Render the live viewer"},
                    "retrieval_count": 2,
                    "created_at": "2026-04-12T09:00:00+00:00",
                    "updated_at": "2026-04-12T10:00:00+00:00",
                    "deleted_at": None,
                }
            ],
            "page_info": {
                "has_next": False,
                "next_cursor": None,
                "returned_count": 1,
                "query": "",
            },
        }

    async def load_team_members(self, _usernames):
        return []

    async def load_recent_sessions_for_authors(self, _usernames):
        return []

    async def get_project_member(self, *, username: str, project: str):
        if username == "rzjulio" and project == "olinkb":
            return {"role": "lead"}
        return None

    async def load_pending_proposals(self, *, project: str, limit: int = 5):
        assert project == "olinkb"
        self.pending_limits.append(limit)
        proposal_count = min(limit, 5 if limit == 5 else 7)
        return {
            "total_count": 7,
            "proposals": [
                {
                    "id": f"pending-{index}",
                    "uri": f"project://olinkb/decisions/pending-{index}",
                    "title": f"Pending {index}",
                    "content": "What: Review this proposal",
                    "memory_type": "decision",
                    "scope": "project",
                    "namespace": "project://olinkb",
                    "author_username": "ana",
                    "proposed_by_username": "ana",
                    "proposed_memory_type": "convention",
                    "approval_status": "pending",
                    "proposal_note": "Make it a convention.",
                    "proposed_at": "2026-04-12T10:00:00+00:00",
                    "metadata": {"what": "Review this proposal"},
                    "tags": [],
                    "retrieval_count": 0,
                    "created_at": "2026-04-12T09:00:00+00:00",
                    "updated_at": "2026-04-12T10:00:00+00:00",
                    "deleted_at": None,
                }
                for index in range(proposal_count)
            ],
        }


@pytest.mark.asyncio
async def test_load_viewer_payload_includes_full_pending_queue_for_approver(monkeypatch) -> None:
    FakeViewerStorage.pending_limits = []
    monkeypatch.setattr(viewer_server, "PostgresStorage", FakeViewerStorage)

    payload = await viewer_server._load_viewer_payload(
        "postgresql://unused",
        params={},
        username="rzjulio",
        team="default-team",
        project="olinkb",
    )

    assert payload["pendingApprovals"]["enabled"] is True
    assert payload["pendingApprovals"]["total_count"] == 7
    assert len(payload["pendingApprovals"]["proposals"]) == 7
    assert FakeViewerStorage.pending_limits == [5, 7]