-- Partial indexes for common query patterns on active memories
CREATE INDEX IF NOT EXISTS idx_memories_active_updated
ON memories(updated_at DESC)
WHERE deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_memories_active_scope_ns
ON memories(scope, namespace)
WHERE deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_memories_pending_proposals
ON memories(namespace, approval_status)
WHERE deleted_at IS NULL AND approval_status = 'pending';

-- Index for open session lookups
CREATE INDEX IF NOT EXISTS idx_sessions_open
ON sessions(author_username, project)
WHERE ended_at IS NULL;
