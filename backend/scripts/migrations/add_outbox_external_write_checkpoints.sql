-- Outbox external write checkpoints migration
-- Description: track which external sinks have been written for idempotent retries

ALTER TABLE outbox_events
    ADD COLUMN IF NOT EXISTS milvus_written_at TIMESTAMP;

ALTER TABLE outbox_events
    ADD COLUMN IF NOT EXISTS neo4j_written_at TIMESTAMP;

CREATE INDEX IF NOT EXISTS idx_outbox_milvus_written_at
    ON outbox_events(milvus_written_at)
    WHERE milvus_written_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_outbox_neo4j_written_at
    ON outbox_events(neo4j_written_at)
    WHERE neo4j_written_at IS NULL;
