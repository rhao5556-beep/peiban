-- Outbox processing timeout migration
-- Description: add processing_started_at column and allow status='pending_review'

ALTER TABLE outbox_events
    ADD COLUMN IF NOT EXISTS processing_started_at TIMESTAMP;

DO $$
DECLARE
    c RECORD;
BEGIN
    FOR c IN
        SELECT conname, pg_get_constraintdef(oid) AS def
        FROM pg_constraint
        WHERE conrelid = 'outbox_events'::regclass
          AND contype = 'c'
    LOOP
        IF c.def ILIKE '%status%' AND c.def ILIKE '%in%' THEN
            EXECUTE format('ALTER TABLE outbox_events DROP CONSTRAINT IF EXISTS %I', c.conname);
        END IF;
    END LOOP;
END $$;

ALTER TABLE outbox_events
    ADD CONSTRAINT outbox_events_status_check
    CHECK (status IN ('pending', 'processing', 'done', 'failed', 'dlq', 'pending_review'));

CREATE INDEX IF NOT EXISTS idx_outbox_processing_started_at
    ON outbox_events(processing_started_at)
    WHERE status = 'processing';
