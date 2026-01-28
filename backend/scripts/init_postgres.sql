-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- 用户表
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    last_active_at TIMESTAMP,
    settings JSONB DEFAULT '{}'
);

-- 会话表
CREATE TABLE sessions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    started_at TIMESTAMP DEFAULT NOW(),
    ended_at TIMESTAMP,
    summary TEXT,
    turn_count INT DEFAULT 0
);

-- 对话轮次表
CREATE TABLE conversation_turns (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    session_id UUID REFERENCES sessions(id) ON DELETE CASCADE,
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    role VARCHAR(10) NOT NULL CHECK (role IN ('user', 'assistant')),
    content TEXT NOT NULL,
    emotion_result JSONB,
    affinity_at_turn FLOAT,
    created_at TIMESTAMP DEFAULT NOW()
);

-- 好感度历史表
CREATE TABLE affinity_history (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    old_score FLOAT NOT NULL,
    new_score FLOAT NOT NULL,
    delta FLOAT NOT NULL,
    trigger_event VARCHAR(50) NOT NULL,
    signals JSONB NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);

-- 记忆表（带状态）
CREATE TABLE memories (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    content TEXT NOT NULL,
    embedding vector(1024),
    valence FLOAT,
    status VARCHAR(20) DEFAULT 'pending' CHECK (status IN ('pending', 'committed', 'deleted')),
    conversation_id UUID,
    created_at TIMESTAMP DEFAULT NOW(),
    committed_at TIMESTAMP
);

-- Outbox事件表（异步写入模式）
CREATE TABLE outbox_events (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    event_id VARCHAR(64) UNIQUE NOT NULL,
    memory_id UUID REFERENCES memories(id) ON DELETE CASCADE,
    payload JSONB NOT NULL,
    status VARCHAR(20) DEFAULT 'pending' CHECK (status IN ('pending', 'processing', 'done', 'failed', 'dlq', 'pending_review')),
    retry_count INT DEFAULT 0,
    idempotency_key VARCHAR(64),
    created_at TIMESTAMP DEFAULT NOW(),
    processing_started_at TIMESTAMP,
    milvus_written_at TIMESTAMP,
    neo4j_written_at TIMESTAMP,
    processed_at TIMESTAMP,
    error_message TEXT
);

-- ID映射表（三方数据一致性）
CREATE TABLE id_mapping (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    postgres_id UUID NOT NULL,
    neo4j_id VARCHAR(100),
    milvus_id BIGINT,
    entity_type VARCHAR(50) NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(user_id, postgres_id)
);

-- 删除审计表
CREATE TABLE deletion_audit (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL,
    deletion_type VARCHAR(50) NOT NULL,
    affected_records JSONB NOT NULL,
    requested_at TIMESTAMP DEFAULT NOW(),
    completed_at TIMESTAMP,
    audit_hash VARCHAR(128) NOT NULL,
    signature TEXT,
    status VARCHAR(20) DEFAULT 'pending' CHECK (status IN ('pending', 'completed', 'failed'))
);

-- 幂等键表（防重复）
CREATE TABLE idempotency_keys (
    key VARCHAR(64) PRIMARY KEY,
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    response JSONB,
    created_at TIMESTAMP DEFAULT NOW(),
    expires_at TIMESTAMP DEFAULT NOW() + INTERVAL '24 hours'
);

-- 索引
CREATE INDEX idx_outbox_status ON outbox_events(status) WHERE status = 'pending';
CREATE INDEX idx_outbox_processing_started_at ON outbox_events(processing_started_at) WHERE status = 'processing';
CREATE INDEX idx_outbox_idempotency ON outbox_events(idempotency_key);
CREATE INDEX idx_memories_status ON memories(status);
CREATE INDEX idx_memories_user ON memories(user_id);
CREATE INDEX idx_idempotency_expires ON idempotency_keys(expires_at);
CREATE INDEX idx_sessions_user ON sessions(user_id);
CREATE INDEX idx_turns_session ON conversation_turns(session_id);
CREATE INDEX idx_affinity_user ON affinity_history(user_id);
CREATE INDEX idx_affinity_user_created_at ON affinity_history(user_id, created_at DESC);

-- 创建更新时间触发器
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_users_updated_at
    BEFORE UPDATE ON users
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();
