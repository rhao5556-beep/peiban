-- Memory Temporal Meta Migration
-- 为 memories 表增加 meta(JSONB) 字段，用于结构化时间等元数据

ALTER TABLE memories
ADD COLUMN IF NOT EXISTS meta JSONB DEFAULT '{}'::jsonb;

CREATE INDEX IF NOT EXISTS idx_memories_meta_gin
ON memories
USING gin (meta);

COMMENT ON COLUMN memories.meta IS '记忆元数据（JSONB），用于 temporal 等结构化信息';

