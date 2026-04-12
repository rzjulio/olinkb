import json

from olinkb.viewer import _extract_note_sections, _normalize_memory, build_viewer_payload, render_viewer_html


def test_build_viewer_payload_creates_relationships_and_counts() -> None:
    payload = build_viewer_payload(
        memories=[
            {
                "id": "m1",
                "uri": "project://olinkb/architecture/core",
                "title": "Arquitectura Core",
                "content": "Base del sistema. Ver tambien project://olinkb/decisions/viewer.",
                "memory_type": "decision",
                "scope": "project",
                "namespace": "project://olinkb",
                "author_username": "rzjulio",
                "tags": ["architecture", "viewer"],
                "retrieval_count": 8,
                "created_at": "2026-04-10T10:00:00+00:00",
                "updated_at": "2026-04-11T10:00:00+00:00",
                "deleted_at": None,
            },
            {
                "id": "m2",
                "uri": "project://olinkb/decisions/viewer",
                "title": "Viewer Read Only",
                "content": "Decision para el sitio read only del proyecto.",
                "memory_type": "decision",
                "scope": "project",
                "namespace": "project://olinkb",
                "author_username": "rzjulio",
                "tags": ["viewer"],
                "retrieval_count": 3,
                "created_at": "2026-04-10T11:00:00+00:00",
                "updated_at": "2026-04-11T11:00:00+00:00",
                "deleted_at": None,
            },
            {
                "id": "m3",
                "uri": "team://conventions/ui-style",
                "title": "UI Style",
                "content": "Visual sobrio y elegante.",
                "memory_type": "convention",
                "scope": "team",
                "namespace": "team://conventions",
                "author_username": "ana",
                "tags": ["style"],
                "retrieval_count": 1,
                "created_at": "2026-04-09T10:00:00+00:00",
                "updated_at": "2026-04-09T10:30:00+00:00",
                "deleted_at": None,
            },
            {
                "id": "m4",
                "uri": "personal://rzjulio/private/scratch",
                "title": "Nota Personal",
                "content": "Esto no debe aparecer en el viewer.",
                "memory_type": "note",
                "scope": "personal",
                "namespace": "personal://rzjulio",
                "author_username": "rzjulio",
                "tags": ["private"],
                "retrieval_count": 5,
                "created_at": "2026-04-10T12:00:00+00:00",
                "updated_at": "2026-04-11T12:00:00+00:00",
                "deleted_at": None,
            },
        ],
        sessions=[
            {
                "id": "s1",
                "author_username": "rzjulio",
                "project": "olinkb",
                "started_at": "2026-04-11T09:00:00+00:00",
                "ended_at": "2026-04-11T11:30:00+00:00",
                "summary": "Trabajo de arquitectura del viewer",
                "memories_read": 4,
                "memories_written": 2,
            }
        ],
        audit_log=[
            {
                "id": 1,
                "timestamp": "2026-04-11T11:15:00+00:00",
                "actor_username": "rzjulio",
                "action": "update",
                "memory_id": "m2",
                "uri": "project://olinkb/decisions/viewer",
                "metadata": {"scope": "project"},
            }
        ],
        team_members=[
            {"username": "rzjulio", "display_name": "Rz Julio", "role": "lead", "team": "mi-equipo"},
            {"username": "ana", "display_name": "Ana", "role": "developer", "team": "mi-equipo"},
        ],
    )

    assert payload["stats"]["memoryCount"] == 3
    assert payload["stats"]["sessionCount"] == 1
    assert payload["stats"]["auditCount"] == 1
    node_ids = {node["id"] for node in payload["graph"]["nodes"]}
    assert {"m1", "m2", "m3"}.issubset(node_ids)
    assert "m4" not in node_ids
    assert "project:olinkb" in node_ids
    assert "project:team/conventions" in node_ids
    assert "type:decision" in node_ids
    assert "type:convention" in node_ids
    graph_nodes = {node["id"]: node for node in payload["graph"]["nodes"]}
    assert graph_nodes["m1"]["projectLabel"] == "olinkb"
    assert graph_nodes["m1"]["stateKey"] == "active"
    assert graph_nodes["m3"]["projectLabel"] == "team/conventions"
    assert graph_nodes["project:olinkb"]["kind"] == "project"
    assert graph_nodes["type:decision"]["kind"] == "memory_type"
    edge_types = {(edge["source"], edge["target"], edge["type"]) for edge in payload["graph"]["edges"]}
    assert ("m1", "m2", "reference") in edge_types
    assert ("m1", "project:olinkb", "belongs_project") in edge_types
    assert ("m1", "type:decision", "has_type") in edge_types
    assert ("m1", "m2", "same_author") in edge_types
    assert ("m1", "m2", "shared_tag") in edge_types
    assert payload["highlights"][0]["uri"] == "project://olinkb/architecture/core"


def test_build_viewer_payload_extracts_teams_projects_and_states() -> None:
    payload = build_viewer_payload(
        memories=[
            {
                "id": "m1",
                "uri": "project://olinkb/architecture",
                "title": "Arquitectura",
                "content": "Contenido",
                "memory_type": "decision",
                "scope": "project",
                "namespace": "project://olinkb",
                "author_username": "rzjulio",
                "tags": [],
                "retrieval_count": 1,
                "created_at": "2026-04-10T10:00:00+00:00",
                "updated_at": "2026-04-11T10:00:00+00:00",
                "deleted_at": None,
            },
            {
                "id": "m2",
                "uri": "team://conventions/coding",
                "title": "Convenciones",
                "content": "Contenido",
                "memory_type": "convention",
                "scope": "team",
                "namespace": "team://conventions",
                "author_username": "ana",
                "tags": [],
                "retrieval_count": 1,
                "created_at": "2026-04-10T10:00:00+00:00",
                "updated_at": "2026-04-11T10:00:00+00:00",
                "deleted_at": None,
            },
        ],
        sessions=[
            {
                "id": "s1",
                "author_username": "ana",
                "project": "olinkb",
                "started_at": "2026-04-11T09:00:00+00:00",
                "ended_at": "2026-04-11T11:30:00+00:00",
                "summary": "Trabajo",
                "memories_read": 1,
                "memories_written": 1,
            }
        ],
        audit_log=[],
        team_members=[
            {"username": "ana", "display_name": "Ana", "role": "developer", "team": "conventions"},
            {"username": "rzjulio", "display_name": "Rz Julio", "role": "lead", "team": "rz-develop"},
        ],
    )

    memories = {memory["id"]: memory for memory in payload["memories"]}
    assert "olinkb" in payload["filters"]["projects"]
    assert "conventions" in payload["filters"]["teams"]
    assert "rz-develop" in payload["filters"]["teams"]
    assert memories["m1"]["team"] == "rz-develop"
    assert memories["m1"]["project"] == "olinkb"
    assert memories["m2"]["team"] == "conventions"
    assert payload["filters"]["established"] == ["active", "deleted"]


def test_build_viewer_payload_preserves_metadata_and_defaults_missing_values() -> None:
    payload = build_viewer_payload(
        memories=[
            {
                "id": "m1",
                "uri": "project://olinkb/decisions/richer-memory-context",
                "title": "Persist richer memory context",
                "content": "What: Persist richer memory context",
                "memory_type": "decision",
                "scope": "project",
                "namespace": "project://olinkb",
                "author_username": "rzjulio",
                "tags": [],
                "metadata": {"what": "Persist richer memory context", "decision": "Store structured metadata"},
                "retrieval_count": 1,
                "created_at": "2026-04-11T10:00:00+00:00",
                "updated_at": "2026-04-11T11:00:00+00:00",
                "deleted_at": None,
            },
            {
                "id": "m2",
                "uri": "project://olinkb/discovery/unstructured-memory",
                "title": "Unstructured memory",
                "content": "Free form note",
                "memory_type": "discovery",
                "scope": "project",
                "namespace": "project://olinkb",
                "author_username": "rzjulio",
                "tags": [],
                "metadata": None,
                "retrieval_count": 0,
                "created_at": "2026-04-11T10:00:00+00:00",
                "updated_at": "2026-04-11T11:00:00+00:00",
                "deleted_at": None,
            },
        ],
        sessions=[],
        audit_log=[],
        team_members=[],
        pending_approvals={
            "enabled": True,
            "total_count": 1,
            "proposals": [
                {
                    "id": "m3",
                    "uri": "project://olinkb/decisions/pending-standard",
                    "title": "Pending standard",
                    "content": "What: Standardize review flow",
                    "memory_type": "decision",
                    "scope": "project",
                    "namespace": "project://olinkb",
                    "author_username": "ana",
                    "proposed_by_username": "ana",
                    "proposed_memory_type": "convention",
                    "approval_status": "pending",
                    "proposal_note": "Make this the default review path.",
                    "proposed_at": "2026-04-11T12:00:00+00:00",
                    "tags": [],
                    "metadata": None,
                    "retrieval_count": 0,
                    "created_at": "2026-04-11T10:00:00+00:00",
                    "updated_at": "2026-04-11T12:00:00+00:00",
                    "deleted_at": None,
                }
            ],
        },
    )

    memories = {memory["id"]: memory for memory in payload["memories"]}

    assert memories["m1"]["metadata"]["what"] == "Persist richer memory context"
    assert memories["m2"]["metadata"] == {}
    assert memories["m1"]["sections"]["what"] == "Persist richer memory context"
    assert memories["m2"]["sections"]["remaining"] == "Free form note"
    assert payload["pendingApprovals"]["enabled"] is True
    assert payload["pendingApprovals"]["proposals"][0]["approval_status"] == "pending"


def test_extract_note_sections_prefers_metadata_and_preserves_remaining_content() -> None:
    sections = _extract_note_sections(
        "Additional context outside sections.\nWhat: Fallback what\nWhy: Raw why",
        {"what": "Structured what", "learned": ["One", "Two"]},
    )

    assert sections["what"] == "Structured what"
    assert sections["why"] == "Raw why"
    assert sections["learned"] == "One\nTwo"
    assert sections["remaining"] == "Additional context outside sections."


def test_normalize_memory_extracts_structured_sections_from_content() -> None:
    normalized = _normalize_memory(
        {
            "id": "m1",
            "uri": "project://olinkb/bugfix/viewer-note-sections",
            "title": "Viewer sections",
            "content": "What: Make notes easier to scan\nWhy: Dense content was hard to read\nWhere: src/olinkb/viewer.py\nLearned: Small structure beats raw blobs",
            "memory_type": "bugfix",
            "scope": "project",
            "namespace": "project://olinkb",
            "author_username": "rzjulio",
            "tags": [],
            "retrieval_count": 0,
            "created_at": "2026-04-12T05:00:00+00:00",
            "updated_at": "2026-04-12T05:00:00+00:00",
            "deleted_at": None,
        }
    )

    assert normalized["sections"]["what"] == "Make notes easier to scan"
    assert normalized["sections"]["why"] == "Dense content was hard to read"
    assert normalized["sections"]["where"] == "src/olinkb/viewer.py"
    assert normalized["sections"]["learned"] == "Small structure beats raw blobs"


def test_render_viewer_html_embeds_serialized_payload() -> None:
    payload = {
        "generatedAt": "2026-04-11T12:00:00+00:00",
        "stats": {"memoryCount": 1, "sessionCount": 0, "auditCount": 0, "authorCount": 1},
        "filters": {"scopes": ["project"], "authors": ["rzjulio"], "tags": ["viewer"], "memoryTypes": ["decision"], "teams": [], "projects": ["olinkb"], "established": ["active", "deleted"]},
        "memories": [{"id": "m1", "title": "Viewer <Read Only>", "content": "Contenido", "uri": "project://olinkb/viewer", "scope": "project", "author_username": "rzjulio", "tags": ["viewer"], "memory_type": "decision", "updated_at": "2026-04-11T12:00:00+00:00"}],
        "sessions": [],
        "auditLog": [],
        "teamMembers": [],
        "graph": {"nodes": [], "edges": []},
        "highlights": [],
    }

    html = render_viewer_html(payload)

    assert "OlinKB Viewer" in html
    assert "Viewer <Read Only>" in html
    assert "window.__OLINKB_VIEWER_DATA__" in html

    serialized = html.split("window.__OLINKB_VIEWER_DATA__ = ", 1)[1].split(";\n", 1)[0]
    parsed = json.loads(serialized)
    assert parsed["stats"]["memoryCount"] == 1


def test_render_viewer_html_supports_live_api_mode() -> None:
    html = render_viewer_html(build_viewer_payload(memories=[], sessions=[], audit_log=[], team_members=[]), live_api_path="/api/viewer")

    assert 'window.__OLINKB_VIEWER_DATA__ = null' in html
    assert 'const liveApiPath = "/api/viewer";' in html
    assert 'window.setInterval(loadLiveData, 10000);' in html
    assert 'const requestUrl = new URL(liveApiPath, window.location.origin);' in html
    assert 'requestUrl.searchParams.set("q", state.search);' in html
    assert 'requestUrl.searchParams.set("cursor", state.live.cursor);' in html
    assert 'requestUrl.searchParams.set("limit", String(state.live.limit));' in html
    assert 'fetch(requestUrl, { cache: "no-store" })' in html
    assert 'data.pageInfo' in html
    assert 'search-pagination' in html


def test_render_viewer_html_supports_persistent_theme_switching_in_static_and_live_modes() -> None:
    payload = build_viewer_payload(memories=[], sessions=[], audit_log=[], team_members=[])

    static_html = render_viewer_html(payload)
    live_html = render_viewer_html(payload, live_api_path="/api/viewer")

    for html in (static_html, live_html):
        assert ':root[data-theme="light"] {' in html
        assert 'color-scheme: dark;' in html
        assert 'color-scheme: light;' in html
        assert 'id="theme-toggle"' in html
        assert 'Appearance' in html
        assert 'const THEME_STORAGE_KEY = "olinkb.viewer.theme";' in html
        assert 'window.localStorage.getItem(THEME_STORAGE_KEY)' in html
        assert 'window.localStorage.setItem(THEME_STORAGE_KEY, theme);' in html
        assert 'document.documentElement.dataset.theme = theme;' in html
        assert 'elements.themeToggle.addEventListener("click", () => {' in html


def test_render_viewer_html_uses_obsidian_like_layout() -> None:
    payload = {
        "generatedAt": "2026-04-11T12:00:00+00:00",
        "stats": {"memoryCount": 1, "activeMemoryCount": 1, "deletedMemoryCount": 0, "sessionCount": 0, "auditCount": 0, "authorCount": 1, "edgeCount": 0},
        "filters": {"scopes": ["project"], "authors": ["rzjulio"], "tags": ["viewer"], "memoryTypes": ["decision"], "teams": [], "projects": ["olinkb"], "established": ["active", "deleted"]},
        "memories": [{"id": "m1", "title": "Viewer", "content": "Contenido", "sections": {"what": "Resumen", "why": "Motivo", "where": "Archivo", "learned": "Aprendizaje", "remaining": ""}, "uri": "project://olinkb/viewer", "scope": "project", "author_username": "rzjulio", "tags": ["viewer"], "memory_type": "decision", "updated_at": "2026-04-11T12:00:00+00:00", "created_at": "2026-04-11T12:00:00+00:00", "namespace": "project://olinkb", "isDeleted": False, "retrieval_count": 1}],
        "sessions": [],
        "auditLog": [],
        "teamMembers": [],
        "graph": {"nodes": [], "edges": []},
        "highlights": [],
        "pendingApprovals": {"enabled": True, "total_count": 2, "proposals": []},
    }

    html = render_viewer_html(payload)

    assert 'class="app-shell"' in html
    assert 'class="sidebar-pane"' in html
    assert 'class="note-pane"' in html
    assert 'class="graph-pane"' in html
    assert 'class="vault-title"' in html
    assert 'class="note-markdown"' in html
    assert 'id="graph-resizer"' in html
    assert 'id="approval-queue"' in html
    assert 'class="explorer-folder"' in html
    assert 'tree-note' in html
    assert 'Directly connected notes' in html
    assert 'Metadata' in html
    assert 'All notes' in html
    assert 'Project' in html
    assert 'buildExplorerTree' in html
    assert 'filter-tree' not in html
    assert 'graph-toggle-btn' not in html
    assert 'class="hero"' not in html
    assert 'Nota abierta' not in html
    assert 'Conexiones directas' not in html
    assert 'Que contiene esta nota' not in html
    assert 'Eventos de cambio' not in html
    assert 'const pixelWidth = Math.round(width * dpr);' in html
    assert 'canvas.width = pixelWidth;' in html
    assert '.graph-pane {' in html and 'overflow: hidden;' in html
    assert 'graphController.resize();' in html
    assert 'new ResizeObserver(() => scheduleResize())' in html
    assert 'projectLabel' in html
    assert 'drawLayoutGuides' in html
    assert 'Active' in html
    assert 'Forgotten' in html
    assert 'node.kind === "project"' in html
    assert 'node.kind === "memory_type"' in html
    assert 'filter((edge) => edge.type === "reference"' in html
    assert 'Math.hypot(moveX, moveY) < 6' in html
    assert 'node.userPosition = true;' in html
    assert 'tree-note-meta' not in html
    assert 'text-overflow: ellipsis;' in html
    assert 'expandedFolders: new Set()' in html
    assert 'details[data-folder-key]' in html
    assert 'note-structured-content' in html
    assert 'note-subsection' in html
    assert 'note-subtitle' in html
    assert 'note-subcontent' in html
    assert 'Additional content' in html
    assert 'const noteSections = selected.sections || {};' in html
    assert 'Pending approvals' in html
    assert 'toggle-pending-view' in html
    assert 'state.viewMode === "pending"' in html
    assert 'pageInfo?.has_next' in html
    assert 'data-live-page="next"' in html
    assert 'data-live-page="prev"' in html