CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";

CREATE TABLE IF NOT EXISTS team_members (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    username TEXT NOT NULL UNIQUE,
    display_name TEXT,
    role TEXT NOT NULL DEFAULT 'developer' CHECK (role IN ('admin', 'lead', 'developer', 'viewer')),
    team TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    is_active BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS memories (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    uri TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    memory_type TEXT NOT NULL CHECK (
        memory_type IN (
            'fact', 'preference', 'event', 'constraint', 'procedure',
            'failure_pattern', 'tool_affordance', 'convention', 'decision', 'discovery'
        )
    ),
    scope TEXT NOT NULL CHECK (scope IN ('personal', 'project', 'team', 'org', 'system')),
    namespace TEXT NOT NULL,
    author_id UUID NOT NULL REFERENCES team_members(id),
    author_username TEXT NOT NULL,
    tags TEXT[] NOT NULL DEFAULT '{}',
    content_hash TEXT NOT NULL,
    vitality_score DOUBLE PRECISION NOT NULL DEFAULT 1.0,
    retrieval_count INTEGER NOT NULL DEFAULT 0,
    last_accessed TIMESTAMPTZ,
    deleted_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_memories_scope ON memories(scope);
CREATE INDEX IF NOT EXISTS idx_memories_namespace ON memories(namespace);
CREATE INDEX IF NOT EXISTS idx_memories_author_username ON memories(author_username);
CREATE INDEX IF NOT EXISTS idx_memories_uri_trgm ON memories USING gin (uri gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_memories_title_trgm ON memories USING gin (title gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_memories_content_trgm ON memories USING gin (content gin_trgm_ops);

CREATE TABLE IF NOT EXISTS sessions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    author_id UUID NOT NULL REFERENCES team_members(id),
    author_username TEXT NOT NULL,
    project TEXT,
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ended_at TIMESTAMPTZ,
    summary TEXT,
    memories_read INTEGER NOT NULL DEFAULT 0,
    memories_written INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS audit_log (
    id BIGSERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    actor_id UUID NOT NULL REFERENCES team_members(id),
    actor_username TEXT NOT NULL,
    action TEXT NOT NULL,
    memory_id UUID REFERENCES memories(id),
    uri TEXT,
    old_content TEXT,
    new_content TEXT,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);
