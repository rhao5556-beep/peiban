# 表情包梗图系统 - 快速入门指南

## MVP 快速启动（5分钟）

本指南帮助你快速启动表情包梗图系统的MVP版本。

## 前置条件

- Docker 和 Docker Compose 已安装
- Python 3.11+
- PostgreSQL、Redis、Neo4j、Milvus 服务运行中

## 步骤1：配置环境变量

复制环境变量模板：

```bash
cd backend
cp .env.example .env
```

编辑 `.env` 文件，添加微博API密钥：

```bash
# 表情包系统配置
WEIBO_API_KEY=your-weibo-api-key-here
WEIBO_API_BASE_URL=https://api.weibo.com/2

# 其他配置使用默认值即可
MEME_SAFETY_SCREENING_ENABLED=true
MEME_SENSOR_INTERVAL_HOURS=1
MEME_TREND_UPDATE_INTERVAL_HOURS=2
MEME_ARCHIVAL_DECLINING_DAYS=30
MEME_DUPLICATE_CHECK_ENABLED=true
```

## 步骤2：运行数据库迁移

执行表情包系统的数据库迁移脚本：

```bash
# 连接到PostgreSQL
docker exec -it affinity-postgres psql -U affinity -d affinity

# 执行迁移脚本
\i /app/scripts/migrations/add_meme_emoji_system.sql

# 退出
\q
```

或者使用命令行：

```bash
docker exec -i affinity-postgres psql -U affinity -d affinity < backend/scripts/migrations/add_meme_emoji_system.sql
```

## 步骤3：启动服务

启动所有服务（如果尚未运行）：

```bash
docker-compose up -d
```

检查服务状态：

```bash
docker-compose ps
```

## 步骤4：验证安装

### 4.1 检查API端点

访问 Swagger 文档：

```
http://localhost:8000/docs
```

查找"表情包"标签下的端点：
- `GET /api/v1/memes/trending`
- `POST /api/v1/memes/feedback`
- `GET /api/v1/memes/stats`
- `GET /api/v1/memes/preferences`
- `PUT /api/v1/memes/preferences`

### 4.2 检查Celery任务

查看Celery worker日志：

```bash
docker-compose logs -f celery-worker
```

应该看到以下任务注册：
- `meme.aggregate_trending_memes`
- `meme.update_meme_scores`
- `meme.archive_old_memes`

### 4.3 检查数据库表

连接到PostgreSQL并验证表已创建：

```bash
docker exec -it affinity-postgres psql -U affinity -d affinity

# 列出表
\dt

# 应该看到：
# - memes
# - meme_usage_history
# - user_meme_preferences

# 查看表结构
\d memes
\d meme_usage_history
\d user_meme_preferences

# 退出
\q
```

## 步骤5：手动触发内容聚合（测试）

### 5.1 使用Flower监控界面

访问 Flower（Celery监控）：

```
http://localhost:5555
```

找到并手动执行任务：
1. 点击 "Tasks"
2. 找到 `meme.aggregate_trending_memes`
3. 点击 "Execute"

### 5.2 使用命令行

```bash
# 进入Celery worker容器
docker exec -it affinity-celery-worker bash

# 手动调用任务
celery -A app.worker call meme.aggregate_trending_memes

# 退出
exit
```

### 5.3 检查结果

查看任务执行日志：

```bash
docker-compose logs celery-worker | grep "meme"
```

查询数据库中的表情包：

```bash
docker exec -it affinity-postgres psql -U affinity -d affinity -c "SELECT id, text_description, status, trend_level FROM memes LIMIT 10;"
```

## 步骤6：测试对话集成

### 6.1 创建测试用户

使用API创建测试用户（如果尚未创建）：

```bash
curl -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "username": "testuser",
    "email": "test@example.com",
    "password": "testpass123"
  }'
```

### 6.2 登录获取Token

```bash
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "username": "testuser",
    "password": "testpass123"
  }'
```

保存返回的 `access_token`。

### 6.3 发送对话消息

```bash
curl -X POST http://localhost:8000/api/v1/conversation/send \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -d '{
    "message": "今天天气真好！",
    "session_id": "test-session-123"
  }'
```

检查响应中是否包含表情包字段：
- `meme_url`
- `meme_description`
- `meme_id`

### 6.4 查看热门表情包

```bash
curl -X GET http://localhost:8000/api/v1/memes/trending?limit=10 \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
```

### 6.5 查看统计信息

```bash
curl -X GET http://localhost:8000/api/v1/memes/stats \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
```

## 步骤7：配置定时任务（可选）

Celery Beat 已自动配置以下定时任务：

- **每小时**：聚合热点表情包
- **每2小时**：更新趋势分数
- **每日**：归档旧表情包

无需额外配置，任务会自动运行。

## 常见问题

### Q1: 微博API密钥在哪里获取？

A: 访问 [微博开放平台](https://open.weibo.com/) 注册开发者账号并创建应用。

### Q2: 为什么没有表情包显示？

A: 可能原因：
1. 内容聚合任务尚未运行（等待1小时或手动触发）
2. 用户好感度分数过低（< 20）
3. 用户选择退出表情包功能
4. 没有合适的表情包匹配当前对话上下文

### Q3: 如何查看Celery任务执行情况？

A: 使用以下方法之一：
1. Flower监控界面：`http://localhost:5555`
2. Celery worker日志：`docker-compose logs -f celery-worker`
3. 数据库查询：检查 `memes` 表中的记录

### Q4: 如何禁用表情包功能？

A: 两种方式：
1. 全局禁用：设置环境变量 `MEME_SAFETY_SCREENING_ENABLED=false`
2. 用户级禁用：调用 `PUT /api/v1/memes/preferences?meme_enabled=false`

### Q5: MVP版本有哪些限制？

A: MVP版本限制：
- 仅支持微博平台
- 仅支持文本和表情符号（无图片）
- 基于关键词的安全筛选和上下文匹配
- 简化的趋势评分公式

## 下一步

1. **监控系统运行**：
   - 查看 Prometheus 指标：`http://localhost:9090`
   - 查看 Grafana 仪表盘：`http://localhost:3001`

2. **调整配置**：
   - 根据实际情况调整聚合频率
   - 优化安全筛选关键词
   - 调整好感度阈值

3. **收集反馈**：
   - 监控接受率指标
   - 分析用户反馈数据
   - 识别改进机会

4. **阶段2增强**：
   - 添加图片表情包支持
   - 集成ML安全检测
   - 实现语义相似度匹配

## 参考资料

- 系统文档：`backend/docs/MEME_EMOJI_SYSTEM.md`
- 设计文档：`.kiro/specs/meme-emoji-system/design.md`
- API文档：`http://localhost:8000/docs`

## 支持

如有问题，请查看：
1. 系统日志：`docker-compose logs`
2. Celery日志：`docker-compose logs celery-worker`
3. API日志：`docker-compose logs api`
4. 故障排除指南：`backend/docs/MEME_EMOJI_SYSTEM.md#故障排除`
