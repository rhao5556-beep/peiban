-- Meme Emoji System Migration
-- Created: 2026-01-18
-- Description: Creates tables for meme content pool, usage history, and user preferences

CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- Memes Table (Content Pool)
CREATE TABLE IF NOT EXISTS memes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- Content fields
    image_url TEXT,                           -- NULL for text-only memes (MVP)
    text_description TEXT NOT NULL,           -- Required: meme text description
    source_platform VARCHAR(50) NOT NULL,     -- 'weibo', 'douyin', 'bilibili'
    category VARCHAR(50),                     -- 'humor', 'emotion', 'trending_phrase'
    
    -- Deduplication and source tracking
    content_hash VARCHAR(64) NOT NULL UNIQUE, -- SHA256(text + normalized_url) for cross-platform deduplication
    original_source_url TEXT,                 -- Original source URL for audit
    
    -- Popularity tracking
    popularity_score FLOAT DEFAULT 0.0,       -- Initial popularity from platform
    trend_score FLOAT DEFAULT 0.0,            -- Calculated trend score (0-100)
    trend_level VARCHAR(20) DEFAULT 'emerging', -- 'emerging', 'rising', 'hot', 'peak', 'declining'
    
    -- Safety and compliance
    safety_status VARCHAR(20) DEFAULT 'pending', -- 'pending', 'approved', 'rejected', 'flagged'
    safety_check_details JSONB,               -- Detailed safety check results for audit
    
    -- Lifecycle tracking
    status VARCHAR(20) DEFAULT 'candidate',   -- 'candidate', 'approved', 'rejected', 'archived'
    first_seen_at TIMESTAMP DEFAULT NOW(),
    last_updated_at TIMESTAMP DEFAULT NOW(),
    
    -- Usage statistics
    usage_count INTEGER DEFAULT 0,
    
    -- Constraints
    CONSTRAINT trend_level_check CHECK (trend_level IN ('emerging', 'rising', 'hot', 'peak', 'declining')),
    CONSTRAINT safety_status_check CHECK (safety_status IN ('pending', 'approved', 'rejected', 'flagged')),
    CONSTRAINT status_check CHECK (status IN ('candidate', 'approved', 'rejected', 'archived')),
    CONSTRAINT trend_score_range CHECK (trend_score >= 0 AND trend_score <= 100),
    CONSTRAINT popularity_score_range CHECK (popularity_score >= 0)
);

-- Query optimization indexes for memes
CREATE INDEX IF NOT EXISTS idx_meme_status_trend ON memes(status, trend_level);
CREATE INDEX IF NOT EXISTS idx_meme_safety_status ON memes(safety_status);
CREATE INDEX IF NOT EXISTS idx_meme_trend_score ON memes(trend_score DESC);
CREATE INDEX IF NOT EXISTS idx_meme_content_hash ON memes(content_hash);
CREATE INDEX IF NOT EXISTS idx_meme_source_platform ON memes(source_platform);
CREATE INDEX IF NOT EXISTS idx_meme_first_seen_at ON memes(first_seen_at DESC);

-- Meme Usage History Table
CREATE TABLE IF NOT EXISTS meme_usage_history (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    meme_id UUID NOT NULL REFERENCES memes(id) ON DELETE CASCADE,
    conversation_id UUID NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    
    used_at TIMESTAMP DEFAULT NOW(),
    user_reaction VARCHAR(20),                -- 'liked', 'ignored', 'disliked'
    
    -- Constraints
    CONSTRAINT user_reaction_check CHECK (user_reaction IN ('liked', 'ignored', 'disliked'))
);

-- Query optimization indexes for meme_usage_history
CREATE INDEX IF NOT EXISTS idx_usage_user_time ON meme_usage_history(user_id, used_at DESC);
CREATE INDEX IF NOT EXISTS idx_usage_meme ON meme_usage_history(meme_id);
CREATE INDEX IF NOT EXISTS idx_usage_conversation ON meme_usage_history(conversation_id);
CREATE INDEX IF NOT EXISTS idx_usage_reaction ON meme_usage_history(user_reaction);

-- User Meme Preferences Table
CREATE TABLE IF NOT EXISTS user_meme_preferences (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    
    meme_enabled BOOLEAN DEFAULT TRUE,        -- User opt-out control
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    
    UNIQUE(user_id)
);

-- Index for user_meme_preferences
CREATE INDEX IF NOT EXISTS idx_user_meme_pref_enabled ON user_meme_preferences(meme_enabled) 
WHERE meme_enabled = TRUE;

-- Create default preferences for existing users (meme enabled by default)
INSERT INTO user_meme_preferences (user_id, meme_enabled)
SELECT id, TRUE FROM users
ON CONFLICT (user_id) DO NOTHING;

-- Add comments for documentation
COMMENT ON TABLE memes IS 'Content pool for memes and trending content with lifecycle tracking';
COMMENT ON TABLE meme_usage_history IS 'History of meme usage in conversations with user feedback';
COMMENT ON TABLE user_meme_preferences IS 'User preferences for meme usage in conversations';

COMMENT ON COLUMN memes.content_hash IS 'SHA256 hash for cross-platform deduplication';
COMMENT ON COLUMN memes.safety_check_details IS 'JSON object containing detailed safety screening results';
COMMENT ON COLUMN memes.trend_score IS 'Calculated trend score (0-100) based on multiple signals';
COMMENT ON COLUMN memes.image_url IS 'NULL for text-only memes in MVP phase';
COMMENT ON COLUMN user_meme_preferences.meme_enabled IS 'User opt-out control - when FALSE, no memes in responses';
