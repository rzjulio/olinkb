ALTER TABLE memories
DROP CONSTRAINT IF EXISTS memories_memory_type_check;

ALTER TABLE memories
ADD CONSTRAINT memories_memory_type_check CHECK (
    memory_type IN (
        'fact', 'preference', 'event', 'constraint', 'procedure',
        'failure_pattern', 'tool_affordance', 'convention', 'decision', 'discovery', 'bugfix'
    )
);