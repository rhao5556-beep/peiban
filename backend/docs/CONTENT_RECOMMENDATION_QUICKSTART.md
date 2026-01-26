# 内容推荐系统 - 快速开始

## 5 分钟快速启动指南

### 前置条件
- Docker 和 Docker Compose 已安装
- 后端服务已运行（PostgreSQL, Neo4j, Redis, Celery）
- 前端开发服务器已启动

### 步骤 1: 数据库迁移

```bash
cd backend
docker exec -it affinity-postgres psql -U affinity -d affinity -f /app/scripts/migrations/add_content_recommendation.sql
```

或者直接在宿主机执行：
```bash
psql -U affinity -d affinity -f backend/scripts/migrations/add_content_recommendation.sql
```

### 步骤 2: 验证 Celery 任务注册

```bash
# 查看已注册的任务
docker exec affinity-celery-worker celery -A app.worker inspect registered

# 应该看到以下任务：
# - app.worker.tasks.content_aggregation.fetch_daily_content
# - app.worker.tasks.content_aggregation.cleanup_old_content
# - app.worker.tasks.content_recommendation.generate_daily_recommendations
```

### 步骤 3: 手动抓取内容

```bash
# 触发内容抓取任务
docker exec affinity-celery-worker celery -A app.worker call app.worker.tasks.content_aggregation.fetch_daily_content

# 查看抓取结果
docker exec -it affinity-postgres psql -U affinity -d affinity -c "SELECT COUNT(*), source FROM content_library GROUP BY source;"
```

### 步骤 4: 提升测试用户好感度

内容推荐需要用户好感度达到 **friend** 或以上。如果你的测试用户好感度不足，可以：

**方法 1: 通过对话提升**
- 在前端聊天界面与 AI 进行多轮对话
- 分享个人信息、兴趣爱好
- 建立记忆图谱

**方法 2: 手动调整（仅用于测试）**
```bash
# 查看当前好感度
docker exec -it affinity-postgres psql -U affinity -d affinity -c "SELECT user_id, old_score, new_score, created_at FROM affinity_history ORDER BY created_at DESC LIMIT 5;"

# 手动插入好感度记录（将 USER_ID 替换为实际用户 ID）
docker exec -it affinity-postgres psql -U affinity -d affinity << EOF
INSERT INTO affinity_history (user_id, old_score, new_score, delta, trigger_event, signals)
VALUES ('USER_ID', 0.3, 0.6, 0.3, 'manual_boost', '{"reason": "test"}');
EOF
```

### 步骤 5: 启用推荐功能

在前端界面：
1. 点击顶部导航的 **"内容推荐"** 标签
2. 滚动到 **"推荐设置"** 区域
3. 打开 **"启用内容推荐"** 开关
4. 设置每日限额（建议 3 条）
5. 点击 **"保存设置"**

或通过 API：
```bash
# 获取 Token
TOKEN=$(curl -X POST http://localhost:8000/api/v1/auth/token \
  -H "Content-Type: application/json" \
  -d '{}' | jq -r '.access_token')

# 启用推荐
curl -X PUT http://localhost:8000/api/v1/content/preference \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "enabled": true,
    "daily_limit": 3,
    "preferred_sources": [],
    "quiet_hours_start": null,
    "quiet_hours_end": null
  }'
```

### 步骤 6: 生成推荐

```bash
# 手动触发推荐生成
docker exec affinity-celery-worker celery -A app.worker call app.worker.tasks.content_recommendation.generate_daily_recommendations

# 查看生成的推荐
docker exec -it affinity-postgres psql -U affinity -d affinity -c "SELECT user_id, COUNT(*) as rec_count FROM recommendation_history WHERE recommended_at >= CURRENT_DATE GROUP BY user_id;"
```

### 步骤 7: 查看推荐

在前端界面：
1. 点击顶部导航的 **"内容推荐"** 标签
2. 查看 **"今日推荐"** 区域
3. 点击标题查看内容（会在新标签页打开）
4. 使用 **"喜欢"** 或 **"不感兴趣"** 按钮提供反馈

或通过 API：
```bash
# 获取推荐
curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/v1/content/recommendations | jq
```

### 步骤 8: 运行 MVP 验证脚本

```bash
cd backend
python test_content_recommendation_mvp.py
```

预期输出：
```
============================================================
内容推荐系统 MVP 功能验证
============================================================
测试时间: 2024-01-18 10:30:00

✓ 创建测试用户: abc-123-def

============================================================
测试 1: 内容聚合服务 (RSS 抓取)
============================================================
✓ 成功抓取 15 条内容

============================================================
测试 2: 用户兴趣提取
============================================================
✓ 提取到 5 个兴趣标签:
  - 技术
  - AI
  - Python
  - 编程
  - 开源

============================================================
测试 3: 好感度门槛验证
============================================================
当前好感度: 60.0 (friend)
✓ 好感度达到 friend，满足推荐条件

============================================================
测试 4: 推荐生成
============================================================
✓ 成功生成 3 条推荐

============================================================
测试结果汇总
============================================================
✓ 通过   内容抓取
✓ 通过   兴趣提取
✓ 通过   好感度门槛
✓ 通过   推荐生成
✓ 通过   每日限额
✓ 通过   API 端点

总计: 6 通过, 0 失败, 0 跳过

🎉 MVP 功能验证通过！
```

## 常见问题

### Q1: 为什么没有推荐？
**A**: 检查以下条件：
1. 好感度是否达到 friend+ （≥40 分）
2. 推荐功能是否已启用
3. 内容库是否有数据
4. 是否已超过每日限额

```bash
# 检查好感度
curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/v1/affinity/history | jq '.[-1]'

# 检查偏好设置
curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/v1/content/preference | jq

# 检查内容库
docker exec -it affinity-postgres psql -U affinity -d affinity -c "SELECT COUNT(*) FROM content_library;"

# 检查今日推荐数
docker exec -it affinity-postgres psql -U affinity -d affinity -c "SELECT COUNT(*) FROM recommendation_history WHERE recommended_at >= CURRENT_DATE;"
```

### Q2: RSS 抓取失败怎么办？
**A**: 检查网络连接和 RSS 源可用性：
```bash
# 查看 Celery 日志
docker-compose logs celery-worker | grep -A 10 "fetch_daily_content"

# 手动测试 RSS 源
curl -I https://example.com/feed.xml
```

### Q3: 如何添加自定义 RSS 源？
**A**: 编辑 `backend/app/services/content_aggregator_service.py`：
```python
RSS_FEEDS = [
    "https://your-custom-feed.com/rss",
    # 添加更多源
]
```
然后重启 Celery worker：
```bash
docker-compose restart celery-worker
```

### Q4: 如何调整推荐算法权重？
**A**: 编辑 `backend/app/services/content_recommendation_service.py`：
```python
# 相似度计算权重
keyword_weight = 0.3  # 关键词匹配
vector_weight = 0.7   # 向量相似度

# 推荐分数权重
similarity_weight = 0.5   # 相似度
recency_weight = 0.3      # 时效性
quality_weight = 0.2      # 质量
```

### Q5: 如何查看 Celery Beat 调度状态？
**A**: 
```bash
# 查看 Beat 日志
docker-compose logs celery-beat | tail -50

# 查看活跃任务
docker exec affinity-celery-worker celery -A app.worker inspect active

# 查看调度计划
docker exec affinity-celery-worker celery -A app.worker inspect scheduled
```

## 下一步

- 📊 查看 [完整文档](./CONTENT_RECOMMENDATION.md)
- 🔧 配置 [监控和告警](./CONTENT_RECOMMENDATION.md#监控指标)
- 🚀 部署到生产环境
- 📈 收集用户反馈并优化算法

## 技术支持

如遇问题，请查看：
- [需求文档](../../.kiro/specs/content-recommendation/requirements.md)
- [设计文档](../../.kiro/specs/content-recommendation/design.md)
- [任务列表](../../.kiro/specs/content-recommendation/tasks.md)
- [API 文档](http://localhost:8000/docs)
