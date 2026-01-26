-- Content Recommendation System Migration
-- Created: 2026-01-18
-- Description: Creates tables for content library, user preferences, and recommendation history

-- Enable pgvector extension if not already enabled
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- Content Library Table (1024-dimensional vectors for bge-m3 compatibility)
CREATE TABLE IF NOT EXISTS content_library (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source VARCHAR(50) NOT NULL,              -- 'rss', 'weibo', 'zhihu', 'bilibili'
    source_url VARCHAR(500) NOT NULL,         -- Original source URL
    title VARCHAR(500) NOT NULL,
    summary TEXT,                             -- Summary (max 500 chars)
    content_url VARCHAR(500) NOT NULL,        -- Content link
    tags TEXT[],                              -- Tag array
    embedding VECTOR(1024),                   -- 1024-dim vector (bge-m3 compatible)
    published_at TIMESTAMP,                   -- Publication time
    fetched_at TIMESTAMP DEFAULT NOW(),       -- Fetch time
    quality_score FLOAT DEFAULT 0.5,          -- Quality score (0-1)
    view_count INTEGER DEFAULT 0,             -- View count (if available)
    is_active BOOLEAN DEFAULT TRUE,           -- Is active
    created_at TIMESTAMP DEFAULT NOW(),
    
    -- Constraints
    CONSTRAINT quality_score_range CHECK (quality_score >= 0 AND quality_score <= 1)
);

-- Indexes for content_library
CREATE INDEX IF NOT EXISTS idx_content_source ON content_library(source);
CREATE INDEX IF NOT EXISTS idx_content_published_at ON content_library(published_at DESC);
CREATE INDEX IF NOT EXISTS idx_content_fetched_at ON content_library(fetched_at DESC);
CREATE INDEX IF NOT EXISTS idx_content_quality_score ON content_library(quality_score DESC);
CREATE INDEX IF NOT EXISTS idx_content_is_active ON content_library(is_active) WHERE is_active = TRUE;

-- Vector index for similarity search (1024-dim)
CREATE INDEX IF NOT EXISTS idx_content_embedding ON content_library 
USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- User Content Preference Table
CREATE TABLE IF NOT EXISTS user_content_preference (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    content_recommendation_enabled BOOLEAN DEFAULT FALSE,  -- Default disabled
    preferred_sources TEXT[],                 -- Preferred sources ['rss', 'bilibili']
    excluded_topics TEXT[],                   -- Excluded topics
    max_daily_recommendations INTEGER DEFAULT 1,
    quiet_hours_start TIME DEFAULT '22:00',
    quiet_hours_end TIME DEFAULT '08:00',
    last_recommendation_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    
    UNIQUE(user_id)
);

-- Index for user_content_preference
CREATE INDEX IF NOT EXISTS idx_user_pref_enabled ON user_content_preference(content_recommendation_enabled) 
WHERE content_recommendation_enabled = TRUE;

-- Recommendation History Table (with delivered_at for accurate CTR calculation)
CREATE TABLE IF NOT EXISTS recommendation_history (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    content_id UUID NOT NULL REFERENCES content_library(id) ON DELETE CASCADE,
    recommended_at TIMESTAMP DEFAULT NOW(),
    delivered_at TIMESTAMP,                   -- Actual delivery time (for CTR calculation)
    clicked_at TIMESTAMP,
    feedback VARCHAR(20),                     -- 'liked', 'disliked', 'ignored'
    feedback_at TIMESTAMP,
    match_score FLOAT,                        -- Match score
    rank_position INTEGER,                    -- Recommendation position (1-3)
    
    -- Constraints
    CONSTRAINT feedback_type CHECK (feedback IN ('clicked', 'liked', 'disliked', 'ignored')),
    CONSTRAINT rank_position_range CHECK (rank_position >= 1 AND rank_position <= 3),
    CONSTRAINT match_score_range CHECK (match_score >= 0 AND match_score <= 1)
);

-- Indexes for recommendation_history
CREATE INDEX IF NOT EXISTS idx_recommendation_user_time ON recommendation_history(user_id, recommended_at DESC);
CREATE INDEX IF NOT EXISTS idx_recommendation_content_time ON recommendation_history(content_id, recommended_at DESC);
CREATE INDEX IF NOT EXISTS idx_recommendation_feedback ON recommendation_history(feedback);
CREATE INDEX IF NOT EXISTS idx_recommendation_delivered ON recommendation_history(delivered_at) 
WHERE delivered_at IS NOT NULL;

-- Create default preferences for existing users
INSERT INTO user_content_preference (user_id, content_recommendation_enabled)
SELECT id, FALSE FROM users
ON CONFLICT (user_id) DO NOTHING;

-- Add comments for documentation
COMMENT ON TABLE content_library IS 'Stores daily fetched content from various sources';
COMMENT ON TABLE user_content_preference IS 'User preferences for content recommendations';
COMMENT ON TABLE recommendation_history IS 'History of recommendations sent to users';

COMMENT ON COLUMN content_library.embedding IS '1024-dimensional vector compatible with BAAI/bge-m3 model';
COMMENT ON COLUMN recommendation_history.delivered_at IS 'Used for accurate CTR calculation (clicks / delivered)';
