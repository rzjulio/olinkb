import pytest

from olinkb.app import OlinKBApp
from olinkb import viewer_server


class FakeViewerStorage:
    pending_limits: list[int] = []

    def __init__(self, *_args, **_kwargs) -> None:
        self.closed = False
        self.search_calls: list[dict[str, object]] = []
        self.created_members: list[dict[str, object]] = []
        self.created_project_members: list[dict[str, object]] = []

    async def connect(self) -> None:
        return None

    async def close(self) -> None:
        self.closed = True

    async def search_viewer_memories(self, **_kwargs):
        self.search_calls.append(dict(_kwargs))
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

    async def count_viewer_memories(self, **_kwargs):
        return 3

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

    async def create_or_update_member(self, username: str, team: str, role: str = "developer", display_name: str | None = None):
        self.created_members.append(
            {
                "username": username,
                "team": team,
                "role": role,
                "display_name": display_name,
            }
        )
        return {
            "id": "member-1",
            "username": username,
            "team": team,
            "role": role,
            "display_name": display_name,
        }

    async def create_or_update_project_member(self, *, member_id, username: str, project: str, team: str, role: str = "developer"):
        self.created_project_members.append(
            {
                "member_id": member_id,
                "username": username,
                "project": project,
                "team": team,
                "role": role,
            }
        )
        return {
            "id": "project-member-1",
            "member_id": member_id,
            "username": username,
            "project": project,
            "team": team,
            "role": role,
        }


class FakeViewerApp:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []
        self.settings = type(
            "Settings",
            (),
            {
                "pg_url": "postgresql://unused",
                "user": "rzjulio",
                "team": "default-team",
                "default_project": "olinkb",
                "cache_ttl_seconds": 300,
                "cache_max_entries": 100,
                "pg_pool_max_size": 5,
                "server_name": "OlinKB",
            },
        )()
        self.storage = type("Storage", (), {"close": self._close})()

    async def _close(self) -> None:
        return None

    async def save_memory(self, **kwargs):
        self.calls.append(kwargs)
        return {"status": "create", "id": "new-1", "uri": kwargs["uri"], "scope": kwargs["scope"]}


@pytest.mark.asyncio
async def test_load_viewer_payload_includes_full_pending_queue_for_approver(monkeypatch) -> None:
    FakeViewerStorage.pending_limits = []
    captured_storage: list[FakeViewerStorage] = []

    def make_storage(*_args, **_kwargs):
        storage = FakeViewerStorage(*_args, **_kwargs)
        captured_storage.append(storage)
        return storage

    monkeypatch.setattr(viewer_server, "PostgresStorage", make_storage)

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
    assert captured_storage[0].search_calls[0]["limit"] == 3
    assert captured_storage[0].search_calls[0]["project"] is None
    assert captured_storage[0].search_calls[0]["team"] is None


@pytest.mark.asyncio
async def test_load_viewer_payload_honors_explicit_project_and_team_filters(monkeypatch) -> None:
    captured_storage: list[FakeViewerStorage] = []

    def make_storage(*_args, **_kwargs):
        storage = FakeViewerStorage(*_args, **_kwargs)
        captured_storage.append(storage)
        return storage

    monkeypatch.setattr(viewer_server, "PostgresStorage", make_storage)

    await viewer_server._load_viewer_payload(
        "postgresql://unused",
        params={"project": ["medical-app"], "team": ["clinical"]},
        username="rzjulio",
        team="default-team",
        project="olinkb",
    )

    assert captured_storage[0].search_calls[0]["project"] == "medical-app"
    assert captured_storage[0].search_calls[0]["team"] == "clinical"


@pytest.mark.asyncio
async def test_load_viewer_payload_keeps_default_page_size_when_limit_is_explicit(monkeypatch) -> None:
    captured_storage: list[FakeViewerStorage] = []

    def make_storage(*_args, **_kwargs):
        storage = FakeViewerStorage(*_args, **_kwargs)
        captured_storage.append(storage)
        return storage

    monkeypatch.setattr(viewer_server, "PostgresStorage", make_storage)

    await viewer_server._load_viewer_payload(
        "postgresql://unused",
        params={"limit": ["10"]},
        username="rzjulio",
        team="default-team",
        project="olinkb",
    )

    assert captured_storage[0].search_calls[0]["limit"] == 10


@pytest.mark.asyncio
async def test_load_viewer_payload_treats_default_limit_as_unfiltered_landing_view(monkeypatch) -> None:
    captured_storage: list[FakeViewerStorage] = []

    def make_storage(*_args, **_kwargs):
        storage = FakeViewerStorage(*_args, **_kwargs)
        captured_storage.append(storage)
        return storage

    monkeypatch.setattr(viewer_server, "PostgresStorage", make_storage)

    await viewer_server._load_viewer_payload(
        "postgresql://unused",
        params={"limit": ["50"]},
        username="rzjulio",
        team="default-team",
        project="olinkb",
    )

    assert captured_storage[0].search_calls[0]["limit"] == 3


def test_normalize_create_memory_payload_builds_global_documentation_defaults() -> None:
    payload = viewer_server._normalize_create_memory_payload(
        {
            "title": "New doc",
            "content": "# Content",
            "memory_type": "documentation",
            "target_scope": "global",
            "file_name": "guide.md",
        },
        role="lead",
        default_project="olinkb",
        default_team="default-team",
    )

    assert payload["scope"] == "org"
    assert payload["scope_key"] == "shared"
    assert payload["metadata"]["documentation_scope"] == "global"
    assert payload["metadata"]["source_file_name"] == "guide.md"


def test_normalize_create_memory_payload_uses_project_scope_for_single_repo_docs() -> None:
    payload = viewer_server._normalize_create_memory_payload(
        {
            "title": "New doc",
            "content": "# Content",
            "memory_type": "documentation",
            "target_scope": "repo",
            "applicable_projects": ["olinkb"],
        },
        role="lead",
        default_project="olinkb",
        default_team="default-team",
    )

    assert payload["scope"] == "project"
    assert payload["scope_key"] == "olinkb"
    assert payload["metadata"]["applicable_projects"] == ["olinkb"]


def test_normalize_create_memory_payload_rejects_development_standard_for_viewer_upload() -> None:
    with pytest.raises(ValueError, match="documentation type must be documentation or business_documentation"):
        viewer_server._normalize_create_memory_payload(
            {
                "title": "New doc",
                "content": "# Content",
                "memory_type": "development_standard",
                "target_scope": "repo",
                "applicable_projects": ["olinkb"],
            },
            role="lead",
            default_project="olinkb",
            default_team="default-team",
        )


def test_normalize_create_memory_payload_blocks_business_docs_for_non_admin() -> None:
    with pytest.raises(viewer_server.ViewerAuthorizationError, match="Only admins can add business documentation"):
        viewer_server._normalize_create_memory_payload(
            {
                "title": "New doc",
                "content": "# Content",
                "memory_type": "business_documentation",
                "target_scope": "global",
            },
            role="lead",
            default_project="olinkb",
            default_team="default-team",
        )


def test_build_memory_uri_generates_expected_note_paths() -> None:
    assert viewer_server._build_memory_uri(scope="project", scope_key="olinkb", title="Nueva doc") == "project://olinkb/notes/nueva-doc"
    assert viewer_server._build_memory_uri(scope="team", scope_key="mi-equipo", title="Nueva doc") == "team://mi-equipo/notes/nueva-doc"
    assert viewer_server._build_memory_uri(scope="system", scope_key="notes", title="Nueva doc") == "system://notes/nueva-doc"


@pytest.mark.asyncio
async def test_create_memory_payload_calls_app_save_memory(monkeypatch) -> None:
    app = FakeViewerApp()
    monkeypatch.setattr(viewer_server, "OlinKBApp", lambda: app)
    monkeypatch.setattr(viewer_server, "PostgresStorage", lambda *_args, **_kwargs: app.storage)

    result = await viewer_server._create_memory_payload(
        "postgresql://unused",
        payload={
            "title": "New doc",
            "content": "# Content",
            "memory_type": "documentation",
            "target_scope": "repo",
            "applicable_projects": ["olinkb"],
            "file_name": "guide.md",
        },
        username="rzjulio",
        role="lead",
        team="default-team",
        project="olinkb",
    )

    assert result["id"] == "new-1"
    assert app.calls[0]["uri"] == "project://olinkb/notes/new-doc"
    assert app.calls[0]["scope"] == "project"
    assert app.calls[0]["author"] == "rzjulio"
    assert app.calls[0]["memory_type"] == "documentation"
    assert app.calls[0]["metadata"]["applicable_projects"] == ["olinkb"]


def test_build_viewer_auth_payload_defaults_to_anonymous() -> None:
    payload = viewer_server._build_viewer_auth_payload(None)

    assert payload == {
        "authenticated": False,
        "username": None,
        "role": None,
        "can_manage_documentation": False,
    }


def test_normalize_login_payload_requires_credentials() -> None:
    with pytest.raises(ValueError, match="username is required"):
        viewer_server._normalize_login_payload({"password": "admin"})

    with pytest.raises(ValueError, match="password is required"):
        viewer_server._normalize_login_payload({"username": "admin"})


def test_authenticate_documentation_session_requires_approver_role() -> None:
    with pytest.raises(PermissionError, match="sign in"):
        viewer_server._authenticate_documentation_session(None)

    with pytest.raises(PermissionError, match="Only admins or leads"):
        viewer_server._authenticate_documentation_session({"username": "dev", "role": "developer"})

    session = viewer_server._authenticate_documentation_session({"username": "admin", "role": "admin"})

    assert session["username"] == "admin"


@pytest.mark.asyncio
async def test_login_viewer_session_provisions_admin_role(monkeypatch) -> None:
    storage = FakeViewerStorage()
    monkeypatch.setattr(viewer_server, "PostgresStorage", lambda *_args, **_kwargs: storage)

    session = await viewer_server._login_viewer_session(
        "postgresql://unused",
        username="admin",
        password="admin",
        team="default-team",
        project="olinkb",
    )

    assert session["username"] == "admin"
    assert session["role"] == "admin"
    assert session["can_manage_documentation"] is True
    assert storage.created_members[0]["role"] == "admin"
    assert storage.created_project_members[0]["role"] == "admin"


@pytest.mark.asyncio
async def test_login_viewer_session_rejects_invalid_credentials() -> None:
    with pytest.raises(PermissionError, match="Invalid viewer credentials"):
        await viewer_server._login_viewer_session(
            "postgresql://unused",
            username="admin",
            password="wrong",
            team="default-team",
            project="olinkb",
        )