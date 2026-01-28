ALTER TABLE user_proactive_preferences
    ADD COLUMN IF NOT EXISTS timezone VARCHAR(64) DEFAULT 'Asia/Shanghai';
