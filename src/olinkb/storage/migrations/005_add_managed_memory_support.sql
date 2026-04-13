ALTER TABLE memories DROP CONSTRAINT IF EXISTS memories_memory_type_check;

ALTER TABLE memories
ADD CONSTRAINT memories_memory_type_check CHECK (
    memory_type IN (
        'fact', 'preference', 'event', 'constraint', 'procedure',
        'failure_pattern', 'tool_affordance', 'convention', 'decision',
        'discovery', 'bugfix',
        'documentation', 'business_documentation', 'development_standard'
    )
);

CREATE TABLE IF NOT EXISTS managed_memory_targets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    memory_id UUID NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
    target_type TEXT NOT NULL CHECK (target_type IN ('global', 'project')),
    target_value TEXT NOT NULL,
    CONSTRAINT managed_memory_targets_target_value_check CHECK (
        (target_type = 'global' AND target_value = '*')
        OR (
            target_type = 'project'
            AND target_value = btrim(target_value)
            AND target_value <> ''
            AND target_value <> '*'
        )
    ),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (memory_id, target_type, target_value)
);

CREATE INDEX IF NOT EXISTS idx_managed_memory_targets_memory_id ON managed_memory_targets(memory_id);
CREATE INDEX IF NOT EXISTS idx_managed_memory_targets_target ON managed_memory_targets(target_type, target_value);