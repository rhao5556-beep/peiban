-- Outbox DLQ Status Migration
-- Created: 2026-01-20
-- Description: allow status='dlq' in outbox_events and ensure pgcrypto exists

CREATE EXTENSION IF NOT EXISTS pgcrypto;

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
