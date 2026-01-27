ALTER TABLE memories ADD COLUMN IF NOT EXISTS observed_at TIMESTAMP NULL;

UPDATE memories
SET observed_at = created_at
WHERE observed_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_memories_user_observed_at
ON memories(user_id, observed_at DESC);

