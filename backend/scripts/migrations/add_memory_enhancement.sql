-- Memory Enhancement Migration
-- 记忆系统增强：上下文记忆、用户画像、响应缓存

CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- ============================================
-- 1. 上下文记忆表 (Context Memory)
-- ============================================
CREATE TABLE IF NOT EXISTS context_memories (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    session_id UUID NOT NULL,
    
    -- 摘要内容
    main_topics TEXT[] NOT NULL DEFAULT '{}',
    key_entities TEXT[] NOT NULL DEFAULT '{}',
    unfinished_threads TEXT[] DEFAULT '{}',
    emotional_arc VARCHAR(20) DEFAULT 'neutral',
    summary_text TEXT NOT NULL,
    
    -- 向量嵌入 (用于语义检索)
    embedding VECTOR(1024),  -- bge-m3 输出维度
    
    -- 重要性和访问统计
    importance_score FLOAT DEFAULT 0.5,
    created_at TIMESTAMP DEFAULT NOW(),
    last_accessed TIMESTAMP DEFAULT NOW(),
    access_count INT DEFAULT 0,
    
    -- 约束
    CONSTRAINT valid_emotional_arc CHECK (emotional_arc IN ('positive', 'negative', 'neutral', 'mixed'))
);

-- 索引
CREATE INDEX IF NOT EXISTS idx_context_memories_user_id ON context_memories(user_id);
CREATE INDEX IF NOT EXISTS idx_context_memories_session_id ON context_memories(session_id);
CREATE INDEX IF NOT EXISTS idx_context_memories_created_at ON context_memories(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_context_memories_importance ON context_memories(user_id, importance_score DESC);

-- 向量索引 (IVFFlat for approximate nearest neighbor search)
CREATE INDEX IF NOT EXISTS idx_context_memories_embedding ON context_memories 
    USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- 注释
COMMENT ON TABLE context_memories IS '上下文记忆表 - 存储跨会话的主题连续性';
COMMENT ON COLUMN context_memories.main_topics IS '会话主要话题列表';
COMMENT ON COLUMN context_memories.key_entities IS '会话中提及的关键实体';
COMMENT ON COLUMN context_memories.unfinished_threads IS '未完成的话题线索';
COMMENT ON COLUMN context_memories.emotional_arc IS '会话情感走向: positive, negative, neutral, mixed';
COMMENT ON COLUMN context_memories.importance_score IS '重要性分数 (0-1)，用于 LRU 淘汰';

-- ============================================
-- 2. 用户画像表 (User Profile)
-- ============================================
CREATE TABLE IF NOT EXISTS user_profiles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID UNIQUE NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    
    -- 性格特征 (范围: -1 到 1)
    introvert_extrovert FLOAT DEFAULT 0,
    optimist_pessimist FLOAT DEFAULT 0,
    analytical_emotional FLOAT DEFAULT 0,
    personality_confidence FLOAT DEFAULT 0,
    
    -- 沟通风格
    avg_message_length FLOAT DEFAULT 0,
    emoji_frequency FLOAT DEFAULT 0,
    question_frequency FLOAT DEFAULT 0,
    response_speed_preference VARCHAR(20) DEFAULT 'moderate',
    
    -- 活跃时间 (JSON array of hours 0-23)
    active_hours JSONB DEFAULT '[]',
    
    -- 话题偏好 (JSON object: topic -> score)
    topic_preferences JSONB DEFAULT '{}',
    
    -- 兴趣标签 (从图谱 LIKES/DISLIKES 聚合)
    interests JSONB DEFAULT '[]',
    
    -- 元数据
    total_messages INT DEFAULT 0,
    total_sessions INT DEFAULT 0,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    
    -- 约束
    CONSTRAINT valid_response_speed CHECK (response_speed_preference IN ('fast', 'moderate', 'thoughtful')),
    CONSTRAINT valid_personality_range CHECK (
        introvert_extrovert BETWEEN -1 AND 1 AND
        optimist_pessimist BETWEEN -1 AND 1 AND
        analytical_emotional BETWEEN -1 AND 1 AND
        personality_confidence BETWEEN 0 AND 1
    )
);

-- 索引
CREATE INDEX IF NOT EXISTS idx_user_profiles_user_id ON user_profiles(user_id);
CREATE INDEX IF NOT EXISTS idx_user_profiles_updated_at ON user_profiles(updated_at);

-- 注释
COMMENT ON TABLE user_profiles IS '用户画像表 - 聚合用户特征和偏好';
COMMENT ON COLUMN user_profiles.introvert_extrovert IS '内向(-1)到外向(1)的性格维度';
COMMENT ON COLUMN user_profiles.optimist_pessimist IS '悲观(-1)到乐观(1)的性格维度';
COMMENT ON COLUMN user_profiles.analytical_emotional IS '理性(-1)到感性(1)的性格维度';
COMMENT ON COLUMN user_profiles.personality_confidence IS '性格分析的置信度 (0-1)';
COMMENT ON COLUMN user_profiles.response_speed_preference IS '响应速度偏好: fast, moderate, thoughtful';

-- 触发器：自动更新 updated_at
CREATE OR REPLACE FUNCTION update_user_profiles_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

DROP TRIGGER IF EXISTS trigger_user_profiles_updated_at ON user_profiles;
CREATE TRIGGER trigger_user_profiles_updated_at
    BEFORE UPDATE ON user_profiles
    FOR EACH ROW
    EXECUTE FUNCTION update_user_profiles_updated_at();

-- ============================================
-- 3. 响应缓存表 (Response Cache)
-- ============================================
CREATE TABLE IF NOT EXISTS response_cache (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    message_pattern VARCHAR(100) NOT NULL,
    affinity_state VARCHAR(20) NOT NULL,
    response TEXT NOT NULL,
    hit_count INT DEFAULT 0,
    created_at TIMESTAMP DEFAULT NOW(),
    expires_at TIMESTAMP NOT NULL,
    
    -- 唯一约束
    CONSTRAINT unique_pattern_state UNIQUE(message_pattern, affinity_state),
    CONSTRAINT valid_affinity_state CHECK (affinity_state IN ('stranger', 'acquaintance', 'friend', 'close_friend', 'best_friend'))
);

-- 索引
CREATE INDEX IF NOT EXISTS idx_response_cache_pattern ON response_cache(message_pattern);
CREATE INDEX IF NOT EXISTS idx_response_cache_expires ON response_cache(expires_at);

-- 注释
COMMENT ON TABLE response_cache IS '响应缓存表 - 缓存常见问候语的回复';
COMMENT ON COLUMN response_cache.message_pattern IS '消息模式 (如 "你好", "早上好")';
COMMENT ON COLUMN response_cache.affinity_state IS '好感度状态';
COMMENT ON COLUMN response_cache.hit_count IS '缓存命中次数';

-- ============================================
-- 4. 清理过期缓存的函数
-- ============================================
CREATE OR REPLACE FUNCTION cleanup_expired_response_cache()
RETURNS INTEGER AS $$
DECLARE
    deleted_count INTEGER;
BEGIN
    DELETE FROM response_cache WHERE expires_at < NOW();
    GET DIAGNOSTICS deleted_count = ROW_COUNT;
    RETURN deleted_count;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION cleanup_expired_response_cache IS '清理过期的响应缓存';

-- ============================================
-- 5. 上下文记忆 LRU 淘汰函数
-- ============================================
CREATE OR REPLACE FUNCTION evict_old_context_memories(
    p_user_id UUID,
    p_max_entries INT DEFAULT 100
)
RETURNS INTEGER AS $$
DECLARE
    deleted_count INTEGER;
    current_count INTEGER;
BEGIN
    -- 获取当前条目数
    SELECT COUNT(*) INTO current_count 
    FROM context_memories 
    WHERE user_id = p_user_id;
    
    -- 如果超过限制，删除最不重要的条目
    IF current_count > p_max_entries THEN
        WITH ranked AS (
            SELECT id,
                   ROW_NUMBER() OVER (
                       ORDER BY (importance_score * 
                           EXTRACT(EPOCH FROM (NOW() - last_accessed)) / 86400.0
                       ) ASC
                   ) as rn
            FROM context_memories
            WHERE user_id = p_user_id
        )
        DELETE FROM context_memories
        WHERE id IN (
            SELECT id FROM ranked WHERE rn > p_max_entries
        );
        
        GET DIAGNOSTICS deleted_count = ROW_COUNT;
    ELSE
        deleted_count := 0;
    END IF;
    
    RETURN deleted_count;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION evict_old_context_memories IS 'LRU 淘汰上下文记忆，保留最重要的 N 条';

