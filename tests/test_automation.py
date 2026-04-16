"""Tests for automation.py - memory classification intelligence."""
import pytest

from olinkb.automation import analyze_memory_candidate


class TestTypeClassification:
    """Tests that verify correct memory type assignment."""

    def test_bugfix_with_structured_fields(self):
        result = analyze_memory_candidate(
            content="What: Fixed crash in login page when user has no email\n"
            "Why: The email field was nullable but the template assumed it was always present\n"
            "Where: src/auth/login.py line 42\n"
            "Learned: Always check nullable fields before template rendering",
            project="myapp",
        )
        assert result["suggested_memory_type"] == "bugfix"
        assert result["action"] == "save"

    def test_decision_with_alternatives(self):
        result = analyze_memory_candidate(
            content="Decision: Use SQLite instead of PostgreSQL for local dev\n"
            "Why: Simpler setup, no Docker needed, faster tests\n"
            "Context: Team evaluated both. Postgres for prod, SQLite for local dev and CI.\n"
            "Evidence: Test suite is 3x faster with SQLite.",
            project="myapp",
        )
        assert result["suggested_memory_type"] == "decision"
        assert result["action"] == "save"

    def test_procedure_with_steps(self):
        result = analyze_memory_candidate(
            content="How to deploy the application:\n"
            "- Step 1: Run the build workflow\n"
            "- Step 2: Install dependencies on the server\n"
            "- Step 3: Run database migrations\n"
            "- Step 4: Restart the application service",
            project="myapp",
        )
        assert result["suggested_memory_type"] == "procedure"

    def test_constraint_detected_without_hint(self):
        result = analyze_memory_candidate(
            content="We cannot use more than 5 database connections because "
            "the cloud provider limits us to 5 concurrent connections per instance. "
            "This is a hard constraint that affects connection pooling.",
            project="myapp",
        )
        assert result["suggested_memory_type"] == "constraint"

    def test_failure_pattern_detected_without_hint(self):
        result = analyze_memory_candidate(
            content="The deploy script fails silently when NODE_ENV is not set. "
            "Symptoms: exit code 0 but no output files. "
            "Workaround: always export NODE_ENV=production before running deploy.sh",
            project="myapp",
        )
        assert result["suggested_memory_type"] == "failure_pattern"

    def test_event_detected_with_hint(self):
        result = analyze_memory_candidate(
            content="Migrated production database from PostgreSQL 14 to 16. "
            "Downtime was 3 minutes. No data loss.",
            project="myapp",
            memory_type_hint="event",
        )
        assert result["suggested_memory_type"] == "event"

    def test_convention_detected_with_hint(self):
        result = analyze_memory_candidate(
            content="All API endpoints must return JSON with a top-level data key. "
            "Error responses use a top-level error key with message and code fields.",
            project="myapp",
            memory_type_hint="convention",
        )
        assert result["suggested_memory_type"] == "convention"

    def test_preference_detected(self):
        result = analyze_memory_candidate(
            content="I prefer dark mode in VS Code with the Monokai theme and 14px font size.",
        )
        assert result["suggested_memory_type"] == "preference"

    def test_fact_fallback_for_generic_content(self):
        result = analyze_memory_candidate(
            content="The production server runs on Ubuntu 22.04 with 16GB RAM.",
            project="myapp",
        )
        assert result["suggested_memory_type"] == "fact"

    def test_discovery_with_insight(self):
        result = analyze_memory_candidate(
            content="Learned: The ORM generates N+1 queries for eager-loaded relations "
            "when using cursor pagination. Turns out the cursor implementation bypasses "
            "the batch loader. Discovered this when profiling slow API responses.",
            project="myapp",
        )
        assert result["suggested_memory_type"] == "discovery"


class TestHintBehavior:
    """Tests that verify memory_type_hint influences classification."""

    def test_hint_makes_type_win(self):
        result = analyze_memory_candidate(
            content="Max 5 DB connections - cloud provider hard limit",
            project="myapp",
            memory_type_hint="constraint",
        )
        assert result["suggested_memory_type"] == "constraint"

    def test_hint_boosts_relevance(self):
        no_hint = analyze_memory_candidate(
            content="Max 5 DB connections per instance",
            project="myapp",
        )
        with_hint = analyze_memory_candidate(
            content="Max 5 DB connections per instance",
            project="myapp",
            memory_type_hint="constraint",
        )
        assert with_hint["relevance_score"] > no_hint["relevance_score"]

    def test_hint_reaches_suggest_threshold(self):
        result = analyze_memory_candidate(
            content="Deploy fails silently without NODE_ENV. Workaround: export NODE_ENV=production",
            project="myapp",
            memory_type_hint="failure_pattern",
        )
        assert result["action"] in ("suggest", "save")

    def test_invalid_hint_ignored(self):
        result = analyze_memory_candidate(
            content="Some generic content about the project setup",
            project="myapp",
            memory_type_hint="not_a_real_type",
        )
        assert result["suggested_memory_type"] != "not_a_real_type"


class TestActionDecision:
    """Tests for save/suggest/skip action decisions."""

    def test_short_content_skips(self):
        result = analyze_memory_candidate(content="updated the readme", project="myapp")
        assert result["action"] == "skip"

    def test_low_signal_phrase_skips(self):
        for phrase in ("ok", "thanks", "done", "listo", "perfect", "gracias", "got it"):
            result = analyze_memory_candidate(content=phrase, project="myapp")
            assert result["action"] == "skip", f"'{phrase}' should skip but got {result['action']}"

    def test_structured_bugfix_auto_saves(self):
        result = analyze_memory_candidate(
            content="What: Fixed null pointer crash in checkout flow\n"
            "Why: Cart items list was not initialized for guest users\n"
            "Where: src/checkout/cart.py line 88\n"
            "Learned: Always initialize collections in constructors",
            project="myapp",
        )
        assert result["action"] == "save"

    def test_generic_fact_skips(self):
        result = analyze_memory_candidate(
            content="The server uses port 8080.",
            project="myapp",
        )
        assert result["action"] == "skip"


class TestWordBoundaryMatching:
    """Tests that keyword matching uses word boundaries correctly."""

    def test_product_does_not_match_production(self):
        """'product' keyword should not match 'production' in content."""
        result = analyze_memory_candidate(
            content="The production server runs on Ubuntu 22.04 with 16GB RAM.",
            project="myapp",
        )
        assert result["suggested_memory_type"] != "business_documentation"

    def test_run_does_not_match_running(self):
        """'run' keyword (if present) should not match 'running'."""
        result = analyze_memory_candidate(
            content="The application was running smoothly after the deployment.",
            project="myapp",
        )
        # Should not classify as procedure just because of "running"
        assert result["suggested_memory_type"] != "procedure"

    def test_fix_matches_fixed(self):
        """'fix' keyword should match 'fixed' via suffix awareness."""
        result = analyze_memory_candidate(
            content="Fixed the login page crash by adding null check to email field. "
            "The error was caused by a missing validation on the email input.",
            project="myapp",
        )
        assert result["suggested_memory_type"] == "bugfix"

    def test_limit_matches_limits(self):
        """'limit' keyword should match 'limits' via suffix awareness."""
        result = analyze_memory_candidate(
            content="The cloud provider limits connections to 5 per instance. "
            "This constraint affects all database pooling configurations.",
            project="myapp",
        )
        assert result["suggested_memory_type"] == "constraint"


class TestScopeInference:
    """Tests for scope inference logic."""

    def test_scope_from_hint(self):
        result = analyze_memory_candidate(
            content="Some important decision about architecture",
            project="myapp",
            scope_hint="team",
        )
        assert result["suggested_scope"] == "team"

    def test_scope_defaults_to_project_when_project_set(self):
        result = analyze_memory_candidate(
            content="Some important decision about architecture",
            project="myapp",
        )
        assert result["suggested_scope"] == "project"

    def test_scope_defaults_to_personal_when_no_project(self):
        result = analyze_memory_candidate(
            content="I prefer using dark mode in my editor",
        )
        assert result["suggested_scope"] == "personal"


class TestTitleInference:
    """Tests for title inference logic."""

    def test_title_from_explicit_param(self):
        result = analyze_memory_candidate(
            content="Some content about a bug",
            project="myapp",
            title="Login page crash fix",
        )
        assert result["suggested_title"] == "Login page crash fix"

    def test_title_from_markdown_heading(self):
        result = analyze_memory_candidate(
            content="# Deploy Pipeline Setup\nSteps to configure the CI/CD pipeline.",
            project="myapp",
        )
        assert result["suggested_title"] == "Deploy Pipeline Setup"

    def test_title_from_structured_field(self):
        result = analyze_memory_candidate(
            content="What: Fixed null pointer in checkout\nWhy: Missing init",
            project="myapp",
        )
        assert "null pointer" in result["suggested_title"].lower() or "checkout" in result["suggested_title"].lower()


class TestURIGeneration:
    """Tests for URI generation."""

    def test_uri_contains_type_bucket(self):
        result = analyze_memory_candidate(
            content="What: Fixed crash in login\nWhy: Null email field",
            project="myapp",
        )
        assert "bugfixes" in result["suggested_uri"]

    def test_all_types_have_buckets(self):
        """All 14 memory types should map to a URI bucket, not 'notes'."""
        from olinkb.automation import TYPE_BUCKETS
        from olinkb.domain import ALLOWED_MEMORY_TYPES

        for memory_type in ALLOWED_MEMORY_TYPES:
            assert memory_type in TYPE_BUCKETS, f"Missing TYPE_BUCKET for {memory_type}"

    def test_uri_project_scope(self):
        result = analyze_memory_candidate(
            content="What: Fixed crash in login\nWhy: Null email field",
            project="myapp",
        )
        assert result["suggested_uri"].startswith("project://myapp/")


class TestMetadataExtraction:
    """Tests for structured metadata extraction."""

    def test_extracts_what_why_where(self):
        result = analyze_memory_candidate(
            content="What: Login crash\nWhy: Null email\nWhere: auth.py line 42",
            project="myapp",
        )
        meta = result["metadata"]
        assert "what" in meta
        assert "why" in meta
        assert "where" in meta

    def test_extracts_decision_context_evidence(self):
        result = analyze_memory_candidate(
            content="Decision: Use SQLite for dev\nContext: Faster than Postgres for tests\nEvidence: 3x speed improvement",
            project="myapp",
        )
        meta = result["metadata"]
        assert "decision" in meta
        assert "context" in meta
        assert "evidence" in meta
