CREATE INDEX IF NOT EXISTS idx_affinity_user_created_at
    ON affinity_history(user_id, created_at DESC);
