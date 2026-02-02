-- Add memory_entities bridge table (Postgres)
-- Purpose: map extracted entities to memories so retrieval can expand by entity without relying on Milvus schema changes.

CREATE TABLE IF NOT EXISTS memory_entities (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    memory_id UUID NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
    entity_id VARCHAR(128) NOT NULL,
    entity_name TEXT,
    entity_type VARCHAR(50),
    confidence FLOAT DEFAULT 0.8,
    source VARCHAR(50) DEFAULT 'llm',
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(user_id, memory_id, entity_id)
);

CREATE INDEX IF NOT EXISTS idx_memory_entities_user_entity
    ON memory_entities(user_id, entity_id);

CREATE INDEX IF NOT EXISTS idx_memory_entities_memory
    ON memory_entities(memory_id);

CREATE INDEX IF NOT EXISTS idx_memory_entities_user_created
    ON memory_entities(user_id, created_at DESC);

