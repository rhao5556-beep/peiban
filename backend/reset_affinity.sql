-- 重置用户好感度为 0
INSERT INTO affinity_history (user_id, old_score, new_score, delta, trigger_event, signals, created_at)
SELECT 
    '9a9e9803-94d6-4ecd-8d09-66fb4745ef85',
    COALESCE((SELECT new_score FROM affinity_history WHERE user_id = '9a9e9803-94d6-4ecd-8d09-66fb4745ef85' ORDER BY created_at DESC LIMIT 1), 100),
    0,
    -100,
    'manual_reset',
    '{"reason": "manual_reset"}'::jsonb,
    NOW();
