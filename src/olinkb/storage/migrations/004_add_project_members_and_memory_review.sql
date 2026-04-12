CREATE TABLE IF NOT EXISTS project_members (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    project TEXT NOT NULL,
    member_id UUID NOT NULL REFERENCES team_members(id),
    username TEXT NOT NULL,
    team TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'developer' CHECK (role IN ('admin', 'lead', 'developer', 'viewer')),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(project, username)
);

CREATE INDEX IF NOT EXISTS idx_project_members_project ON project_members(project);
CREATE INDEX IF NOT EXISTS idx_project_members_username ON project_members(username);

ALTER TABLE memories
ADD COLUMN IF NOT EXISTS approval_status TEXT NOT NULL DEFAULT 'approved'
    CHECK (approval_status IN ('approved', 'pending', 'rejected'));

ALTER TABLE memories
ADD COLUMN IF NOT EXISTS proposed_memory_type TEXT;

ALTER TABLE memories
ADD COLUMN IF NOT EXISTS proposed_by UUID REFERENCES team_members(id);

ALTER TABLE memories
ADD COLUMN IF NOT EXISTS proposed_by_username TEXT;

ALTER TABLE memories
ADD COLUMN IF NOT EXISTS proposed_at TIMESTAMPTZ;

ALTER TABLE memories
ADD COLUMN IF NOT EXISTS proposal_note TEXT;

ALTER TABLE memories
ADD COLUMN IF NOT EXISTS reviewed_by UUID REFERENCES team_members(id);

ALTER TABLE memories
ADD COLUMN IF NOT EXISTS reviewed_by_username TEXT;

ALTER TABLE memories
ADD COLUMN IF NOT EXISTS reviewed_at TIMESTAMPTZ;

ALTER TABLE memories
ADD COLUMN IF NOT EXISTS review_note TEXT;

CREATE INDEX IF NOT EXISTS idx_memories_approval_status ON memories(approval_status);
CREATE INDEX IF NOT EXISTS idx_memories_pending_project_reviews ON memories(namespace, approval_status)
    WHERE approval_status = 'pending';