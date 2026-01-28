-- 主动消息表
CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE TABLE IF NOT EXISTS proactive_messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    trigger_type VARCHAR(50) NOT NULL,
    trigger_rule_id VARCHAR(100),
    content TEXT NOT NULL,
    scheduled_at TIMESTAMP NOT NULL,
    sent_at TIMESTAMP,
    delivered_at TIMESTAMP,
    read_at TIMESTAMP,
    user_response VARCHAR(20),  -- replied, ignored, disabled
    status VARCHAR(20) NOT NULL DEFAULT 'pending',  -- pending, sent, delivered, read, cancelled, ignored
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP DEFAULT NOW(),
    
    -- 索引
    CONSTRAINT valid_status CHECK (status IN ('pending', 'sent', 'delivered', 'read', 'cancelled', 'ignored')),
    CONSTRAINT valid_response CHECK (user_response IS NULL OR user_response IN ('replied', 'ignored', 'disabled'))
);

-- 索引优化
CREATE INDEX IF NOT EXISTS idx_proactive_messages_user_id ON proactive_messages(user_id);
CREATE INDEX IF NOT EXISTS idx_proactive_messages_status ON proactive_messages(status);
CREATE INDEX IF NOT EXISTS idx_proactive_messages_scheduled ON proactive_messages(scheduled_at) WHERE status = 'pending';
CREATE INDEX IF NOT EXISTS idx_proactive_messages_sent_date ON proactive_messages(DATE(sent_at));

-- 用户偏好设置表
CREATE TABLE IF NOT EXISTS user_proactive_preferences (
    user_id UUID PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    proactive_enabled BOOLEAN DEFAULT TRUE,
    morning_greeting BOOLEAN DEFAULT TRUE,
    evening_greeting BOOLEAN DEFAULT FALSE,
    silence_reminder BOOLEAN DEFAULT TRUE,
    event_reminder BOOLEAN DEFAULT TRUE,
    quiet_hours_start TIME DEFAULT '22:00',
    quiet_hours_end TIME DEFAULT '08:00',
    max_daily_messages INTEGER DEFAULT 2,
    preferred_greeting_time TIME,
    timezone VARCHAR(64) DEFAULT 'Asia/Shanghai',
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- 触发器：自动更新 updated_at
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger WHERE tgname = 'update_user_proactive_preferences_updated_at'
    ) THEN
        EXECUTE $sql$
            CREATE TRIGGER update_user_proactive_preferences_updated_at
                BEFORE UPDATE ON user_proactive_preferences
                FOR EACH ROW
                EXECUTE FUNCTION update_updated_at_column();
        $sql$;
    END IF;
END $$;

-- 注释
COMMENT ON TABLE proactive_messages IS '主动消息记录表';
COMMENT ON COLUMN proactive_messages.trigger_type IS '触发类型: time, silence, decay, event, weather, emotion';
COMMENT ON COLUMN proactive_messages.user_response IS '用户响应: replied(回复了), ignored(忽略了), disabled(关闭了)';

COMMENT ON TABLE user_proactive_preferences IS '用户主动消息偏好设置';
COMMENT ON COLUMN user_proactive_preferences.quiet_hours_start IS '免打扰开始时间';
COMMENT ON COLUMN user_proactive_preferences.quiet_hours_end IS '免打扰结束时间';
