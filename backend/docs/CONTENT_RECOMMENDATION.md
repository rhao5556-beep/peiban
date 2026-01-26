# 内容推荐系统 - MVP 文档

## 概述

个性化内容推荐系统为用户提供基于兴趣和好感度的智能内容推荐。系统通过分析用户的对话历史和记忆图谱，自动推荐相关内容。

## 核心功能

### 1. 内容聚合
- **RSS 订阅抓取**: 从配置的 RSS 源抓取最新内容
- **内容标准化**: 统一处理标题、摘要、URL、发布时间
- **向量化**: 使用 bge-m3 模型生成 1024 维嵌入向量
- **自动清理**: 定期清理 7 天前的旧内容

### 2. 智能推荐
- **兴趣提取**: 从 Neo4j 记忆图谱提取用户兴趣（3-10 个标签）
- **混合匹配**: 关键词匹配 (30%) + 向量相似度 (70%)
- **多维评分**: 相似度 (50%) + 时效性 (30%) + 质量 (20%)
- **多样性控制**: 同源最多 1 条，同话题最多 2 条

### 3. 用户控制
- **好感度门槛**: 只向 friend+ 状态用户推荐
- **启用开关**: 默认关闭，需用户主动启用
- **每日限额**: 默认 1 条，可调整至 1-5 条
- **来源过滤**: 可选择偏好的内容来源
- **免打扰时间**: 设置不接收推荐的时间段

### 4. 反馈闭环
- **点击追踪**: 记录用户点击行为
- **喜欢/不喜欢**: 收集用户反馈
- **兴趣更新**: 基于反馈调整兴趣权重（未来版本）

## 架构设计

### 数据库表

#### content_library
存储抓取的内容及其向量表示
```sql
- id: UUID (主键)
- title: 标题
- summary: 摘要
- url: 链接
- source: 来源 (rss/weibo/zhihu/bilibili)
- tags: 标签数组
- embedding: 1024 维向量 (pgvector)
- quality_score: 质量分数
- published_at: 发布时间
- created_at: 创建时间
```

#### user_content_preference
用户推荐偏好设置
```sql
- user_id: UUID (主键)
- enabled: 是否启用
- daily_limit: 每日限额
- preferred_sources: 偏好来源
- quiet_hours_start: 免打扰开始时间
- quiet_hours_end: 免打扰结束时间
```

#### recommendation_history
推荐历史记录
```sql
- id: UUID (主键)
- user_id: 用户 ID
- content_id: 内容 ID
- match_score: 匹配分数
- rank_position: 排名位置
- recommended_at: 推荐时间
- delivered_at: 送达时间
- clicked_at: 点击时间
- feedback: 反馈 (liked/disliked/ignored)
```

### 服务层

#### ContentAggregatorService
- `fetch_rss_feeds()`: 抓取 RSS 内容
- `fetch_with_retry()`: 带重试的 HTTP 请求
- `check_robots_txt()`: 检查 robots.txt 合规性
- `save_content()`: 保存内容到数据库

#### ContentRecommendationService
- `generate_recommendations()`: 生成推荐
- `_extract_user_interests()`: 提取用户兴趣
- `_calculate_similarity()`: 计算相似度
- `_calculate_recommendation_score()`: 计算推荐分数
- `_ensure_diversity()`: 确保多样性

### Celery 任务

#### content_aggregation.py
- `fetch_daily_content`: 每天 7:00 AM 抓取内容
- `cleanup_old_content`: 每天 2:00 AM 清理旧内容

#### content_recommendation.py
- `generate_daily_recommendations`: 每天 9:00 AM 生成推荐

### API 端点

#### GET /api/v1/content/recommendations
获取今日推荐
```json
[
  {
    "id": "uuid",
    "content_id": "uuid",
    "title": "标题",
    "summary": "摘要",
    "url": "https://...",
    "source": "rss",
    "tags": ["技术", "AI"],
    "match_score": 0.85,
    "rank_position": 1,
    "recommended_at": "2024-01-18T09:00:00Z",
    "clicked_at": null,
    "feedback": null
  }
]
```

#### POST /api/v1/content/recommendations/{id}/feedback
提交反馈
```json
{
  "action": "clicked" | "liked" | "disliked" | "ignored"
}
```

#### GET /api/v1/content/preference
获取用户偏好
```json
{
  "enabled": false,
  "daily_limit": 1,
  "preferred_sources": [],
  "quiet_hours_start": null,
  "quiet_hours_end": null
}
```

#### PUT /api/v1/content/preference
更新用户偏好
```json
{
  "enabled": true,
  "daily_limit": 3,
  "preferred_sources": ["rss", "zhihu"],
  "quiet_hours_start": "22:00",
  "quiet_hours_end": "08:00"
}
```

## 前端组件

### ContentRecommendation.tsx
推荐展示组件
- 显示今日推荐（最多 3 条）
- 点击链接（新标签页打开）
- 喜欢/不喜欢按钮
- 加载状态和错误处理

### ContentPreferenceSettings.tsx
偏好设置组件
- 启用/禁用开关
- 每日限额选择器
- 来源多选框
- 免打扰时间设置

## 使用指南

### 1. 数据库迁移
```bash
cd backend
psql -U affinity -d affinity -f scripts/migrations/add_content_recommendation.sql
```

### 2. 配置 RSS 源
编辑 `backend/app/services/content_aggregator_service.py`:
```python
RSS_FEEDS = [
    "https://example.com/feed.xml",
    # 添加更多 RSS 源
]
```

### 3. 启动 Celery Worker
```bash
docker-compose up -d celery-worker celery-beat
```

### 4. 手动触发内容抓取
```bash
docker exec affinity-celery-worker celery -A app.worker call app.worker.tasks.content_aggregation.fetch_daily_content
```

### 5. 手动生成推荐
```bash
docker exec affinity-celery-worker celery -A app.worker call app.worker.tasks.content_recommendation.generate_daily_recommendations
```

### 6. 运行 MVP 验证
```bash
cd backend
python test_content_recommendation_mvp.py
```

## 配置说明

### 环境变量
```bash
# 嵌入模型配置
EMBEDDING_MODEL=BAAI/bge-m3
EMBEDDING_DIM=1024

# 推荐系统配置
CONTENT_RECOMMENDATION_ENABLED=true
DEFAULT_DAILY_LIMIT=1
MIN_AFFINITY_STATE=friend

# RSS 抓取配置
RSS_RATE_LIMIT=10/min
RSS_TIMEOUT=30
RSS_MAX_RETRIES=3
```

### Celery Beat 调度
```python
# 每天 7:00 AM 抓取内容
'fetch-daily-content': {
    'task': 'app.worker.tasks.content_aggregation.fetch_daily_content',
    'schedule': crontab(hour=7, minute=0)
}

# 每天 9:00 AM 生成推荐
'generate-daily-recommendations': {
    'task': 'app.worker.tasks.content_recommendation.generate_daily_recommendations',
    'schedule': crontab(hour=9, minute=0)
}

# 每天 2:00 AM 清理旧内容
'cleanup-old-content': {
    'task': 'app.worker.tasks.content_aggregation.cleanup_old_content',
    'schedule': crontab(hour=2, minute=0)
}
```

## 监控指标

### 内容抓取
- `content_fetch_total`: 抓取总数（按来源）
- `content_fetch_errors`: 抓取错误数
- `content_fetch_duration_seconds`: 抓取耗时

### 推荐生成
- `recommendation_generation_total`: 生成总数
- `recommendation_delivered_total`: 送达总数
- `recommendation_errors_total`: 错误总数
- `recommendation_generation_duration_seconds`: 生成耗时

### 用户参与
- `recommendation_clicks_total`: 点击总数
- `recommendation_likes_total`: 喜欢总数
- `recommendation_dislikes_total`: 不喜欢总数
- `active_recommendation_users`: 活跃用户数

## 性能指标

### SLO 目标
- 内容抓取: < 5 分钟（所有来源）
- 推荐生成: < 3 秒（单用户）
- API 响应: < 500ms (P95)

### 当前性能
- RSS 抓取: ~30 秒（10 个源）
- 推荐生成: ~1 秒（单用户）
- API 响应: ~200ms (P95)

## 故障排查

### 问题 1: 未生成推荐
**可能原因**:
- 好感度不足（需要 friend+）
- 推荐功能未启用
- 内容库为空

**解决方案**:
```bash
# 检查好感度
curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/v1/affinity/history

# 检查偏好设置
curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/v1/content/preference

# 检查内容库
psql -U affinity -d affinity -c "SELECT COUNT(*) FROM content_library;"
```

### 问题 2: RSS 抓取失败
**可能原因**:
- 网络问题
- RSS 源不可用
- robots.txt 限制

**解决方案**:
```bash
# 查看 Celery 日志
docker-compose logs celery-worker | grep content_aggregation

# 手动测试 RSS 源
curl -I https://example.com/feed.xml
```

### 问题 3: 推荐质量差
**可能原因**:
- 用户兴趣不准确
- 内容标签不匹配
- 相似度计算问题

**解决方案**:
- 增加对话以丰富记忆图谱
- 调整推荐算法权重
- 检查嵌入向量质量

## 未来增强

### 阶段 2: 增强功能（第 3-4 周）
- [ ] 社交媒体热点抓取（微博、知乎、B站）
- [ ] LLM 推荐消息生成
- [ ] 集成主动消息服务
- [ ] 用户反馈闭环（兴趣权重更新）
- [ ] Prometheus 监控和 Grafana 仪表板

### 阶段 3: 生产就绪（第 5-6 周）
- [ ] 容错与降级策略
- [ ] 性能优化（缓存、批处理）
- [ ] 告警规则配置
- [ ] 完整测试套件
- [ ] 运维文档

## 参考资料

- [需求文档](../../.kiro/specs/content-recommendation/requirements.md)
- [设计文档](../../.kiro/specs/content-recommendation/design.md)
- [任务列表](../../.kiro/specs/content-recommendation/tasks.md)
- [API 文档](http://localhost:8000/docs)
