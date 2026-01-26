-- 冲突解决系统 - 数据库迁移
-- 添加冲突状态字段和相关表

CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- 1. 为 memories 表添加冲突状态字段
ALTER TABLE memories 
ADD COLUMN IF NOT EXISTS conflict_status VARCHAR(20) DEFAULT 'active';

-- 可能的值：
-- 'active': 活跃记忆（默认）
-- 'deprecated': 已废弃（被新记忆替代）
-- 'conflicted': 存在冲突（需要澄清）

-- 添加索引以提高查询性能
CREATE INDEX IF NOT EXISTS idx_memories_conflict_status 
ON memories(conflict_status);

-- 2. 创建冲突记录表
CREATE TABLE IF NOT EXISTS memory_conflicts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    memory_1_id UUID NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
    memory_2_id UUID NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
    conflict_type VARCHAR(50) NOT NULL, -- 'opposite', 'contradiction', 'inconsistent'
    common_topic TEXT[], -- 共同主题（如 ['茶', '饮料']）
    confidence FLOAT NOT NULL DEFAULT 0.0, -- 冲突置信度 (0-1)
    status VARCHAR(20) NOT NULL DEFAULT 'pending', -- 'pending', 'resolved', 'ignored'
    resolution_method VARCHAR(50), -- 'user_clarified', 'time_priority', 'auto_merged'
    preferred_memory_id UUID REFERENCES memories(id), -- 用户选择的正确记忆
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    resolved_at TIMESTAMP,
    metadata JSONB, -- 额外信息（如澄清问题、用户回答等）
    
    -- 确保不会重复记录同一对冲突
    UNIQUE(memory_1_id, memory_2_id)
);

-- 添加索引
CREATE INDEX IF NOT EXISTS idx_conflicts_user_id ON memory_conflicts(user_id);
CREATE INDEX IF NOT EXISTS idx_conflicts_status ON memory_conflicts(status);
CREATE INDEX IF NOT EXISTS idx_conflicts_created_at ON memory_conflicts(created_at DESC);

-- 3. 创建澄清会话表（记录澄清对话）
CREATE TABLE IF NOT EXISTS clarification_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    conflict_id UUID NOT NULL REFERENCES memory_conflicts(id) ON DELETE CASCADE,
    session_id UUID NOT NULL, -- 对话会话 ID
    clarification_question TEXT NOT NULL, -- 澄清问题
    user_response TEXT, -- 用户回答
    status VARCHAR(20) NOT NULL DEFAULT 'pending', -- 'pending', 'answered', 'timeout'
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    answered_at TIMESTAMP
);

-- 添加索引
CREATE INDEX IF NOT EXISTS idx_clarification_user_id ON clarification_sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_clarification_status ON clarification_sessions(status);
CREATE INDEX IF NOT EXISTS idx_clarification_session_id ON clarification_sessions(session_id);

-- 4. 添加注释
COMMENT ON TABLE memory_conflicts IS '记忆冲突记录表 - 存储检测到的矛盾记忆';
COMMENT ON TABLE clarification_sessions IS '澄清会话表 - 记录向用户询问澄清的对话';

COMMENT ON COLUMN memories.conflict_status IS '记忆冲突状态：active(活跃), deprecated(已废弃), conflicted(存在冲突)';
COMMENT ON COLUMN memory_conflicts.conflict_type IS '冲突类型：opposite(对立), contradiction(矛盾), inconsistent(不一致)';
COMMENT ON COLUMN memory_conflicts.confidence IS '冲突置信度 (0-1)，越高表示越确定存在冲突';
COMMENT ON COLUMN memory_conflicts.status IS '冲突状态：pending(待处理), resolved(已解决), ignored(已忽略)';
COMMENT ON COLUMN memory_conflicts.resolution_method IS '解决方法：user_clarified(用户澄清), time_priority(时间优先), auto_merged(自动合并)';

-- 5. 创建视图：活跃记忆（排除已废弃的）
CREATE OR REPLACE VIEW active_memories AS
SELECT * FROM memories
WHERE conflict_status = 'active'
AND status = 'committed';

-- 6. 创建视图：待处理冲突
CREATE OR REPLACE VIEW pending_conflicts AS
SELECT 
    mc.*,
    m1.content as memory_1_content,
    m1.created_at as memory_1_created_at,
    m2.content as memory_2_content,
    m2.created_at as memory_2_created_at
FROM memory_conflicts mc
JOIN memories m1 ON mc.memory_1_id = m1.id
JOIN memories m2 ON mc.memory_2_id = m2.id
WHERE mc.status = 'pending'
ORDER BY mc.created_at DESC;

-- 7. 创建函数：标记记忆为已废弃
CREATE OR REPLACE FUNCTION deprecate_memory(memory_id_param UUID)
RETURNS VOID AS $$
BEGIN
    UPDATE memories
    SET conflict_status = 'deprecated'
    WHERE id = memory_id_param;
END;
$$ LANGUAGE plpgsql;

-- 8. 创建函数：解决冲突
CREATE OR REPLACE FUNCTION resolve_conflict(
    conflict_id_param UUID,
    preferred_memory_id_param UUID,
    resolution_method_param VARCHAR(50)
)
RETURNS VOID AS $$
DECLARE
    other_memory_id UUID;
BEGIN
    -- 更新冲突状态
    UPDATE memory_conflicts
    SET 
        status = 'resolved',
        preferred_memory_id = preferred_memory_id_param,
        resolution_method = resolution_method_param,
        resolved_at = NOW()
    WHERE id = conflict_id_param;
    
    -- 获取另一条记忆的 ID
    SELECT CASE 
        WHEN memory_1_id = preferred_memory_id_param THEN memory_2_id
        ELSE memory_1_id
    END INTO other_memory_id
    FROM memory_conflicts
    WHERE id = conflict_id_param;
    
    -- 标记非首选记忆为已废弃
    IF other_memory_id IS NOT NULL THEN
        PERFORM deprecate_memory(other_memory_id);
    END IF;
END;
$$ LANGUAGE plpgsql;

-- 9. 示例数据（可选，用于测试）
-- INSERT INTO memory_conflicts (user_id, memory_1_id, memory_2_id, conflict_type, common_topic, confidence)
-- VALUES (
--     'user-uuid-here',
--     'memory-1-uuid',
--     'memory-2-uuid',
--     'opposite',
--     ARRAY['茶'],
--     0.9
-- );

-- 完成
SELECT 'Conflict resolution schema migration completed successfully!' as status;
