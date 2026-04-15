from __future__ import annotations

from dataclasses import dataclass
import re
import unicodedata
from typing import Any

from olinkb.domain import ALLOWED_SCOPES, MANAGED_MEMORY_TYPES, parse_tags


STRUCTURED_METADATA_PATTERN = re.compile(
    r"^(?P<label>What|Why|Where|Learned|Context|Decision|Evidence|Next(?:\s+|_)?Steps|Goal|Instructions|Discoveries|Accomplished):\s*(?P<value>.*?)(?=^(?:What|Why|Where|Learned|Context|Decision|Evidence|Next(?:\s+|_)?Steps|Goal|Instructions|Discoveries|Accomplished):|\Z)",
    re.IGNORECASE | re.MULTILINE | re.DOTALL,
)
WORD_PATTERN = re.compile(r"[a-z0-9]+(?:[-_][a-z0-9]+)*", re.IGNORECASE)
SLUG_PATTERN = re.compile(r"[^a-z0-9]+")
TITLE_MAX_LENGTH = 80
AUTO_SAVE_THRESHOLD = 70
SUGGEST_THRESHOLD = 42
DOC_SUGGEST_THRESHOLD = 55
HIGH_CONFIDENCE_DOC_THRESHOLD = 78

TYPE_BUCKETS = {
    "bugfix": "bugfixes",
    "decision": "decisions",
    "procedure": "procedures",
    "discovery": "discoveries",
    "documentation": "documentation",
    "business_documentation": "business-documentation",
    "development_standard": "development-standards",
}

KEYWORDS = {
    "bugfix": (
        "bug",
        "bugfix",
        "fix",
        "fixed",
        "regression",
        "root cause",
        "error",
        "failure",
        "incident",
        "broken",
    ),
    "decision": (
        "decision",
        "tradeoff",
        "chose",
        "chosen",
        "opted",
        "prefer",
        "keep",
        "adopt",
        "approach",
    ),
    "procedure": (
        "steps",
        "step",
        "run",
        "command",
        "install",
        "setup",
        "workflow",
        "how to",
        "procedure",
        "guide",
    ),
    "discovery": (
        "learned",
        "discovered",
        "found",
        "observed",
        "realized",
        "insight",
        "gotcha",
        "pattern",
    ),
    "documentation": (
        "architecture",
        "overview",
        "documentation",
        "documentacion",
        "handbook",
        "readme",
        "api",
        "contract",
        "end-to-end",
        "how it works",
        "design",
    ),
    "business_documentation": (
        "business",
        "stakeholder",
        "roadmap",
        "customer",
        "product",
        "policy",
        "functional",
        "quarter",
        "revenue",
    ),
    "development_standard": (
        "standard",
        "standards",
        "convention",
        "guideline",
        "rule",
        "must",
        "should",
        "always",
        "never",
        "naming",
        "style",
    ),
}

LOW_SIGNAL_PHRASES = {
    "ok",
    "okay",
    "thanks",
    "thank you",
    "done",
    "listo",
    "perfect",
}


@dataclass(frozen=True)
class AnalysisContext:
    content: str
    title: str | None
    project: str | None
    scope_hint: str | None
    memory_type_hint: str | None
    tags: list[str]
    metadata: dict[str, Any]
    source_surface: str
    files: list[str]
    commands: list[str]
    author: str | None


def analyze_memory_candidate(
    *,
    content: str,
    title: str | None = None,
    project: str | None = None,
    scope_hint: str | None = None,
    memory_type_hint: str | None = None,
    tags: str | list[str] = "",
    metadata: dict[str, Any] | None = None,
    source_surface: str = "cli",
    files: list[str] | None = None,
    commands: list[str] | None = None,
    author: str | None = None,
) -> dict[str, Any]:
    normalized_content = (content or "").strip()
    if not normalized_content:
        raise ValueError("content is required")

    normalized_scope = (scope_hint or "").strip().lower() or None
    if normalized_scope is not None and normalized_scope not in ALLOWED_SCOPES:
        raise ValueError(f"Unsupported scope hint: {scope_hint}")

    context = AnalysisContext(
        content=normalized_content,
        title=(title or "").strip() or None,
        project=(project or "").strip() or None,
        scope_hint=normalized_scope,
        memory_type_hint=(memory_type_hint or "").strip().lower() or None,
        tags=parse_tags(tags),
        metadata={str(key): value for key, value in (metadata or {}).items() if value not in (None, "")},
        source_surface=(source_surface or "cli").strip() or "cli",
        files=[str(value).strip() for value in (files or []) if str(value).strip()],
        commands=[str(value).strip() for value in (commands or []) if str(value).strip()],
        author=(author or "").strip() or None,
    )

    extracted_metadata = _extract_metadata_from_content(context.content)
    merged_metadata = {**extracted_metadata, **context.metadata}
    type_scores, signals = _compute_type_scores(context, merged_metadata)
    suggested_memory_type = _select_memory_type(type_scores)
    suggested_scope = _infer_scope(context)
    suggested_title = _infer_title(context, merged_metadata, suggested_memory_type)
    suggested_tags = _build_tags(context, suggested_memory_type, suggested_scope)
    metadata_out = _build_metadata(context, merged_metadata, suggested_memory_type, suggested_scope, type_scores)
    suggested_uri = _build_uri(
        suggested_memory_type=suggested_memory_type,
        suggested_scope=suggested_scope,
        suggested_title=suggested_title,
        project=context.project,
        author=context.author,
    )
    documentation_candidate = suggested_memory_type in MANAGED_MEMORY_TYPES
    relevance_score = _compute_relevance_score(type_scores, signals, documentation_candidate)
    reasons = _build_reasons(type_scores, signals, suggested_memory_type, documentation_candidate)
    action = _choose_action(
        relevance_score=relevance_score,
        documentation_candidate=documentation_candidate,
        suggested_memory_type=suggested_memory_type,
        suggested_scope=suggested_scope,
    )

    return {
        "action": action,
        "should_save": action != "skip",
        "relevance_score": relevance_score,
        "suggested_title": suggested_title,
        "suggested_memory_type": suggested_memory_type,
        "suggested_scope": suggested_scope,
        "suggested_uri": suggested_uri,
        "suggested_tags": suggested_tags,
        "reasons": reasons,
        "signals": signals,
        "metadata": metadata_out,
        "documentation_candidate": documentation_candidate,
        "project": context.project,
        "source_surface": context.source_surface,
    }


def _compute_type_scores(context: AnalysisContext, metadata: dict[str, Any]) -> tuple[dict[str, int], dict[str, Any]]:
    normalized_content = _normalize_text(context.content)
    normalized_title = _normalize_text(context.title or "")
    normalized_text = f"{normalized_title}\n{normalized_content}".strip()
    word_count = len(WORD_PATTERN.findall(normalized_content))
    structured_fields = sorted(metadata)
    markdown_heading_count = sum(1 for line in context.content.splitlines() if line.lstrip().startswith("#"))
    bullet_count = sum(1 for line in context.content.splitlines() if line.lstrip().startswith(("- ", "* "))) 
    file_count = len(context.files)
    command_count = len(context.commands)

    signals = {
        "word_count": word_count,
        "structured_fields": structured_fields,
        "markdown_heading_count": markdown_heading_count,
        "bullet_count": bullet_count,
        "file_count": file_count,
        "command_count": command_count,
        "source_surface": context.source_surface,
    }

    scores = {memory_type: 0 for memory_type in KEYWORDS}
    for memory_type, keywords in KEYWORDS.items():
        for keyword in keywords:
            if keyword in normalized_text:
                scores[memory_type] += 12 if " " in keyword else 8

    if "this document" in normalized_text or "document explains" in normalized_text:
        scores["documentation"] += 14
    if "architecture guide" in normalized_text or "architecture" in normalized_title:
        scores["documentation"] += 12

    if word_count >= 24:
        for memory_type in scores:
            scores[memory_type] += 8
    if word_count >= 50:
        for memory_type in scores:
            scores[memory_type] += 6

    structure_bonus = min(len(structured_fields), 4) * 7
    for memory_type in ("bugfix", "decision", "procedure", "discovery"):
        scores[memory_type] += structure_bonus

    if markdown_heading_count:
        scores["documentation"] += 16 + min(markdown_heading_count, 3) * 4
        scores["business_documentation"] += 8
        scores["development_standard"] += 6

    if bullet_count:
        scores["procedure"] += min(bullet_count, 4) * 5
        scores["documentation"] += min(bullet_count, 4) * 2

    if file_count:
        scores["bugfix"] += min(file_count, 3) * 5
        scores["decision"] += min(file_count, 3) * 3
        scores["documentation"] += min(file_count, 3) * 3

    if command_count:
        scores["procedure"] += min(command_count, 4) * 5
        scores["bugfix"] += min(command_count, 3) * 2
        scores["documentation"] += min(command_count, 2) * 2

    if context.memory_type_hint and context.memory_type_hint in scores:
        scores[context.memory_type_hint] += 15

    lowered_content = normalized_content.strip()
    if lowered_content in LOW_SIGNAL_PHRASES:
        for memory_type in scores:
            scores[memory_type] = 0

    return scores, signals


def _select_memory_type(type_scores: dict[str, int]) -> str:
    priority = [
        "business_documentation",
        "development_standard",
        "documentation",
        "bugfix",
        "procedure",
        "decision",
        "discovery",
    ]
    best_score = max(type_scores.values())
    if best_score <= 0:
        return "fact"
    for memory_type in priority:
        if type_scores[memory_type] == best_score:
            return memory_type
    return "fact"


def _compute_relevance_score(type_scores: dict[str, int], signals: dict[str, Any], documentation_candidate: bool) -> int:
    best_score = max(type_scores.values()) if type_scores else 0
    score = min(95, best_score)
    if signals["structured_fields"]:
        score += min(len(signals["structured_fields"]), 4) * 4
    if signals["file_count"]:
        score += min(signals["file_count"], 2) * 4
    if signals["command_count"]:
        score += min(signals["command_count"], 2) * 3
    if documentation_candidate and signals["markdown_heading_count"]:
        score += 6
    if signals["word_count"] < 10:
        score -= 20
    elif signals["word_count"] < 20:
        score -= 8
    return max(0, min(99, score))


def _build_reasons(
    type_scores: dict[str, int],
    signals: dict[str, Any],
    suggested_memory_type: str,
    documentation_candidate: bool,
) -> list[str]:
    reasons: list[str] = []
    if signals["structured_fields"]:
        reasons.append(f"Structured fields detected: {', '.join(signals['structured_fields'])}")
    if signals["file_count"]:
        reasons.append(f"References {signals['file_count']} file(s), which makes the note more reusable")
    if signals["command_count"]:
        reasons.append(f"Includes {signals['command_count']} command(s), which suggests operational value")
    if documentation_candidate:
        reasons.append("Content looks like reusable documentation rather than a one-off note")
    elif suggested_memory_type != "fact":
        reasons.append(f"Strongest inferred memory type is {suggested_memory_type}")
    else:
        reasons.append("Content has low specificity, so it falls back to a generic factual note")
    if max(type_scores.values()) <= 0:
        reasons.append("No strong durable-memory signals were detected")
    return reasons


def _choose_action(
    *,
    relevance_score: int,
    documentation_candidate: bool,
    suggested_memory_type: str,
    suggested_scope: str,
) -> str:
    if relevance_score < SUGGEST_THRESHOLD:
        return "skip"
    if suggested_memory_type == "business_documentation":
        return "suggest"
    if suggested_scope in {"org", "team", "system"}:
        return "suggest" if documentation_candidate or relevance_score < 85 else "save"
    if documentation_candidate:
        if relevance_score >= HIGH_CONFIDENCE_DOC_THRESHOLD and suggested_scope == "project":
            return "save"
        return "suggest" if relevance_score >= DOC_SUGGEST_THRESHOLD else "skip"
    return "save" if relevance_score >= AUTO_SAVE_THRESHOLD else "suggest"


def _infer_scope(context: AnalysisContext) -> str:
    if context.scope_hint:
        return context.scope_hint
    if context.project:
        return "project"
    return "personal"


def _infer_title(context: AnalysisContext, metadata: dict[str, Any], suggested_memory_type: str) -> str:
    if context.title:
        return context.title

    for line in context.content.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            heading = stripped.lstrip("#").strip()
            if heading:
                return heading[:TITLE_MAX_LENGTH]

    for key in ("decision", "what", "goal", "accomplished", "learned"):
        value = metadata.get(key)
        if value:
            return _truncate_title(str(value))

    first_line = next((line.strip() for line in context.content.splitlines() if line.strip()), suggested_memory_type)
    return _truncate_title(first_line)


def _build_tags(context: AnalysisContext, suggested_memory_type: str, suggested_scope: str) -> list[str]:
    tags = list(context.tags)
    normalized_source = _slugify(context.source_surface)
    if normalized_source and normalized_source not in tags:
        tags.append(normalized_source)
    if suggested_memory_type not in tags:
        tags.append(suggested_memory_type)
    if suggested_scope == "project" and context.project and context.project not in tags:
        tags.append(context.project)
    return tags


def _build_metadata(
    context: AnalysisContext,
    metadata: dict[str, Any],
    suggested_memory_type: str,
    suggested_scope: str,
    type_scores: dict[str, int],
) -> dict[str, Any]:
    metadata_out = dict(metadata)
    metadata_out["source_surface"] = context.source_surface
    metadata_out["automation"] = {
        "suggested_memory_type": suggested_memory_type,
        "type_scores": type_scores,
    }
    if context.files:
        metadata_out.setdefault("related_files", context.files)
    if context.commands:
        metadata_out.setdefault("related_commands", context.commands)

    if suggested_memory_type in MANAGED_MEMORY_TYPES:
        metadata_out.setdefault("managed", True)
        metadata_out.setdefault("content_format", "markdown")
        metadata_out.setdefault("documentation_scope", "repo" if suggested_scope == "project" else "global")
        if suggested_scope == "project" and context.project:
            metadata_out.setdefault("applicable_projects", [context.project])

    return metadata_out


def _build_uri(
    *,
    suggested_memory_type: str,
    suggested_scope: str,
    suggested_title: str,
    project: str | None,
    author: str | None,
) -> str:
    bucket = TYPE_BUCKETS.get(suggested_memory_type, "notes")
    slug = _slugify(suggested_title) or "note"
    if suggested_scope == "project":
        scope_key = project or "shared"
        return f"project://{scope_key}/{bucket}/{slug}"
    if suggested_scope == "personal":
        scope_key = author or "user"
        return f"personal://{scope_key}/{bucket}/{slug}"
    if suggested_scope == "team":
        return f"team://shared/{bucket}/{slug}"
    if suggested_scope == "org":
        return f"org://shared/{bucket}/{slug}"
    return f"system://shared/{bucket}/{slug}"


def _extract_metadata_from_content(content: str) -> dict[str, str]:
    metadata: dict[str, str] = {}
    for match in STRUCTURED_METADATA_PATTERN.finditer(content):
        label = re.sub(r"[\s_]+", " ", match.group("label").strip().lower())
        value = match.group("value").strip()
        if not value:
            continue
        key = "next_steps" if label == "next steps" else label
        metadata[key] = value
    return metadata


def _normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii")
    return ascii_value.lower()


def _truncate_title(value: str) -> str:
    compact = re.sub(r"\s+", " ", value).strip()
    if len(compact) <= TITLE_MAX_LENGTH:
        return compact
    return compact[: TITLE_MAX_LENGTH - 1].rstrip() + "…"


def _slugify(value: str) -> str:
    normalized = _normalize_text(value)
    return SLUG_PATTERN.sub("-", normalized).strip("-")