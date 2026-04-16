import json

from olinkb.templates import (
    render_cli_mandatory_prompt_template,
    render_instructions_template,
    render_mcp_template,
    render_memory_relevance_skill_template,
)


def test_render_mcp_template_uses_mcp_alias() -> None:
    rendered = render_mcp_template(
        pg_url="postgresql://olinkb:olinkb@localhost:5433/olinkb",
        team="example-team",
    )

    config = json.loads(rendered)

    assert config["servers"]["olinkb"]["command"] == "olinkb"
    assert config["servers"]["olinkb"]["args"] == ["mcp"]
    assert config["servers"]["olinkb"]["type"] == "stdio"
    assert config["servers"]["olinkb"]["env"]["OLINKB_TEAM"] == "example-team"


def test_render_instructions_mentions_boot_and_end_session() -> None:
    rendered = render_instructions_template()

    assert "boot_session" in rendered
    assert "remember" in rendered
    assert "save_memory" in rendered
    assert "end_session" in rendered
    assert "forget" in rendered


def test_render_instructions_encourages_richer_context_blocks() -> None:
    rendered = render_instructions_template()

    assert "default memory workflow across repositories" in rendered
    assert "richer context blocks" in rendered
    assert "Do not wait until `end_session`" in rendered
    assert "Do not save a one-line summary" in rendered
    assert "real operational depth" in rendered
    assert "What:" in rendered
    assert "Why:" in rendered
    assert "Where:" in rendered
    assert "Learned:" in rendered
    assert "Context:" in rendered
    assert "Decision:" in rendered
    assert "Evidence:" in rendered
    assert "Next Steps:" in rendered
    assert "without reopening every touched file first" in rendered
    assert "include_content=false" in rendered
    assert "explicitly calls `propose_memory_promotion(...)`" in rendered
    assert "specialized repository skill exists" in rendered


def test_render_instructions_mcp_has_mandatory_gate() -> None:
    rendered = render_instructions_template(mode="mcp")

    assert "### Mandatory Gate" in rendered
    assert "Do not use internal chat memory" in rendered
    assert "Do not answer project-memory questions from guesswork" in rendered
    assert "Do not claim a memory was persisted unless" in rendered
    assert "Failure policy:" in rendered
    assert "If `boot_session` fails" in rendered
    assert "If `remember` fails" in rendered
    assert "If `capture_memory` or `save_memory` fails" in rendered
    assert "If `end_session` fails" in rendered
    assert "Do not begin project analysis, planning, or implementation before calling `boot_session`" in rendered


def test_render_instructions_includes_memory_type_guide() -> None:
    for mode in ("mcp", "cli"):
        rendered = render_instructions_template(mode=mode)

        assert "### Memory Type Selection" in rendered
        assert "`decision`" in rendered
        assert "`discovery`" in rendered
        assert "`bugfix`" in rendered
        assert "`procedure`" in rendered
        assert "`convention`" in rendered
        assert "`constraint`" in rendered
        assert "`failure_pattern`" in rendered
        assert "`tool_affordance`" in rendered
        assert "`fact`" in rendered


def test_render_instructions_includes_scope_guide() -> None:
    for mode in ("mcp", "cli"):
        rendered = render_instructions_template(mode=mode)

        assert "### Scope Selection" in rendered
        assert "`personal`" in rendered
        assert "`project`" in rendered
        assert "`team`" in rendered


def test_render_instructions_mentions_forget() -> None:
    for mode in ("mcp", "cli"):
        rendered = render_instructions_template(mode=mode)

        assert "forget" in rendered
        assert "soft-delete" in rendered


def test_render_memory_relevance_skill_template_contains_triage_contract() -> None:
    rendered = render_memory_relevance_skill_template()

    assert "name: memory-relevance-triage" in rendered
    assert "## Decision Rule" in rendered
    assert "## Result-Aware Triage" in rendered
    assert "## Output Contract" in rendered
    assert "SAVE" in rendered
    assert "SKIP" in rendered
    assert "## How to Persist" in rendered
    assert "save_memory" in rendered
    assert "capture_memory" in rendered
    assert "forget" in rendered
    assert "## Memory Type Selection" in rendered
    assert "`decision`" in rendered
    assert "`bugfix`" in rendered
    assert "## Scope Selection" in rendered
    assert "`project`" in rendered
    assert "`scope`" in rendered


def test_render_cli_instructions_switches_transport_language() -> None:
    rendered = render_instructions_template(mode="cli")

    assert "via the local OlinKB CLI transport" in rendered
    assert "### Mandatory CLI Gate" in rendered
    assert "OlinKB CLI usage is required for project memory workflows" in rendered
    assert "Do not use internal chat memory, `/memories/`, or session summaries as a substitute" in rendered
    assert "If `boot_session` fails, do not start project analysis, planning, or implementation" in rendered
    assert "If `remember` fails for a question that depends on prior project context" in rendered
    assert "If `capture_memory` or `save_memory` fails for a durable result" in rendered
    assert "If `end_session` fails, report that session closure was not recorded" in rendered
    assert "olinkb tool boot_session --json" in rendered
    assert "run the corresponding `olinkb tool ...` command" in rendered
    assert "analyze_memory" in rendered
    assert "capture_memory" in rendered
    assert "Treat these as mandatory checkpoints, not best-effort suggestions" in rendered
    assert "Do not begin project analysis, planning, or implementation before running `boot_session`" in rendered
    assert "`end_session` is mandatory session closure, but it never replaces earlier `capture_memory` or `save_memory` calls" in rendered
    assert "On Windows PowerShell, do not use bash-style escaping" in rendered
    assert "ConvertTo-Json -Compress" in rendered
    assert "--input-file" in rendered
    assert "MCP tools" not in rendered
    assert "### Available Tools" in rendered
    assert "`forget`" in rendered


def test_render_cli_mandatory_prompt_template_enforces_olinkb_cli_workflow() -> None:
    rendered = render_cli_mandatory_prompt_template()

    assert "mode: agent" in rendered
    assert "mandatory OlinKB CLI memory workflow" in rendered
    assert "Use OlinKB CLI as a mandatory workflow, not optional guidance" in rendered
    assert "Before any project analysis, planning, implementation, or project-context answer" in rendered
    assert "Run `olinkb tool boot_session --json ...`" in rendered
    assert "Before answering anything about prior work, conventions, decisions, bugs, procedures, or project history" in rendered
    assert "Run `olinkb tool remember --json ...`" in rendered
    assert "Run `olinkb tool analyze_memory --json ...` or `olinkb tool capture_memory --json ...`" in rendered
    assert "If the result is clearly durable and was not persisted automatically, run `olinkb tool save_memory --json ...`" in rendered
    assert "Run `olinkb tool end_session --json ...`" in rendered
    assert "Do not substitute internal chat memory, `/memories/`, or a session summary for OlinKB" in rendered
    assert "On Windows PowerShell, do not emit bash-style escaped JSON" in rendered
    assert "If any required OlinKB command fails, stop that workflow step, explain the failure, and ask whether to continue without OlinKB" in rendered
    assert "propose_memory_promotion" in rendered
    assert "forget" in rendered
    assert "memory_type" in rendered
    assert "scope" in rendered