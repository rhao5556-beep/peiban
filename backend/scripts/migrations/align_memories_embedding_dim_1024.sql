-- Align memories.embedding to vector(1024)

CREATE EXTENSION IF NOT EXISTS vector;

ALTER TABLE memories
    ADD COLUMN IF NOT EXISTS embedding_new vector(1024);

UPDATE memories
SET embedding_new = CASE
    WHEN embedding IS NULL THEN NULL
    WHEN vector_dims(embedding) = 1024 THEN embedding
    ELSE NULL
END;

ALTER TABLE memories
    DROP COLUMN IF EXISTS embedding;

ALTER TABLE memories
    RENAME COLUMN embedding_new TO embedding;
