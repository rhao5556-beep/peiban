# 快速部署指南 - 生产环境

## 前置条件

- Docker 和 Docker Compose 已安装
- 已获取 SiliconFlow API Key（必需）
- 服务器至少 4GB RAM

---

## 5 分钟快速部署

### 步骤 1: 克隆代码并配置环境变量

```bash
# 进入后端目录
cd backend

# 复制环境变量模板
cp .env.example .env

# 编辑配置文件
nano .env
```

**必需修改的配置**:
```env
# LLM 配置（必需）
OPENAI_API_KEY=sk-your-siliconflow-api-key-here

# JWT 密钥（必需修改为随机字符串）
JWT_SECRET=your-super-secret-key-change-in-production-$(openssl rand -hex 32)

# 数据库密码（建议修改）
DATABASE_URL=postgresql://affinity:your_strong_password@localhost:5432/affinity
NEO4J_PASSWORD=your_neo4j_password
```

### 步骤 2: 启动所有服务

```bash
# 启动所有容器
docker-compose up -d

# 等待服务启动（约 30 秒）
sleep 30

# 检查服务状态
docker-compose ps
```

**预期输出**:
```
NAME                    STATUS
affinity-api            Up
affinity-postgres       Up (healthy)
affinity-neo4j          Up
affinity-milvus         Up
affinity-redis          Up
affinity-celery-worker  Up
```

### 步骤 3: 初始化数据库

```bash
# 初始化 PostgreSQL
docker exec -it affinity-postgres psql -U affinity -d affinity -f /app/scripts/init_postgres.sql

# 运行所有迁移
docker exec -it affinity-postgres psql -U affinity -d affinity -f /app/scripts/migrations/add_memory_enhancement.sql
docker exec -it affinity-postgres psql -U affinity -d affinity -f /app/scripts/migrations/add_content_recommendation.sql
docker exec -it affinity-postgres psql -U affinity -d affinity -f /app/scripts/migrations/add_meme_emoji_system.sql
docker exec -it affinity-postgres psql -U affinity -d affinity -f /app/scripts/migrations/add_conflict_resolution.sql
docker exec -it affinity-postgres psql -U affinity -d affinity -f /app/scripts/migrations/add_proactive_messages.sql
```

### 步骤 4: 验证部署

```bash
# 测试 API 健康
curl http://localhost:8000/health

# 测试 LLM 连接
python test_llm.py

# 测试 Celery Worker
docker exec affinity-celery-worker celery -A app.worker inspect active
```

### 步骤 5: 访问应用

- **API 文档**: http://localhost:8000/docs
- **前端应用**: http://localhost:5173
- **Neo4j 浏览器**: http://localhost:7474 (neo4j/your_neo4j_password)
- **Flower 监控**: http://localhost:5555

---

## 功能验证清单

### ✅ 核心功能

```bash
# 1. 测试对话功能
curl -X POST http://localhost:8000/api/v1/conversation/message \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{"message": "你好，我是张三"}'

# 2. 测试记忆存储
# 发送几条消息后，检查记忆
docker exec -it affinity-postgres psql -U affinity -d affinity -c \
  "SELECT id, content, status FROM memories ORDER BY created_at DESC LIMIT 5;"

# 3. 测试图谱构建
# 等待 Outbox 处理（约 2-5 秒）
docker exec -it affinity-neo4j cypher-shell -u neo4j -p your_neo4j_password \
  "MATCH (n) RETURN labels(n), count(n);"

# 4. 测试向量检索
# 发送查询消息，观察是否能检索到相关记忆
curl -X POST http://localhost:8000/api/v1/conversation/message \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{"message": "我叫什么名字？"}'
```

### ✅ 内容推荐功能

```bash
# 测试内容抓取（使用 RSSHub 公开 API）
docker exec affinity-celery-worker celery -A app.worker call \
  app.worker.tasks.content_aggregation.test_fetch_content

# 查看抓取的内容
docker exec -it affinity-postgres psql -U affinity -d affinity -c \
  "SELECT source, title FROM content_library ORDER BY fetched_at DESC LIMIT 10;"
```

### ✅ 表情包功能

```bash
# 测试表情包抓取（使用 RSSHub 微博热搜）
docker exec affinity-celery-worker celery -A app.worker call \
  app.worker.tasks.meme_aggregation.aggregate_trending_memes

# 查看抓取的表情包
docker exec -it affinity-postgres psql -U affinity -d affinity -c \
  "SELECT text_description, source_platform, status FROM memes ORDER BY created_at DESC LIMIT 10;"
```

### ⚠️ 主动消息功能（需要配置推送服务）

```bash
# 测试触发逻辑（不会实际推送，只记录到数据库）
docker exec affinity-celery-worker celery -A app.worker call \
  app.worker.tasks.proactive.check_proactive_triggers

# 查看待发送消息
docker exec -it affinity-postgres psql -U affinity -d affinity -c \
  "SELECT user_id, trigger_type, content, status FROM proactive_messages ORDER BY created_at DESC LIMIT 5;"
```

---

## 常见问题排查

### 问题 1: LLM API 调用失败

**症状**: 对话无响应或返回错误

**排查**:
```bash
# 检查 API Key 是否配置
grep OPENAI_API_KEY .env

# 测试 LLM 连接
python test_llm.py

# 查看 API 日志
docker-compose logs -f api | grep "LLM"
```

**解决方案**:
- 确认 API Key 正确
- 确认 SiliconFlow 账户有余额
- 检查网络连接

### 问题 2: Celery Worker 未启动

**症状**: 记忆一直显示 "pending"

**排查**:
```bash
# 检查 Worker 状态
docker-compose ps affinity-celery-worker

# 查看 Worker 日志
docker-compose logs -f celery-worker

# 检查任务注册
docker exec affinity-celery-worker celery -A app.worker inspect registered
```

**解决方案**:
```bash
# 重启 Worker
docker-compose restart celery-worker

# 如果缺少依赖，进入容器安装
docker exec -it affinity-celery-worker bash
pip install feedparser bilibili-api-python circuitbreaker
```

### 问题 3: 数据库连接失败

**症状**: API 启动失败或查询报错

**排查**:
```bash
# 检查 PostgreSQL
docker exec -it affinity-postgres psql -U affinity -d affinity -c "SELECT 1;"

# 检查 Neo4j
docker exec -it affinity-neo4j cypher-shell -u neo4j -p your_password "RETURN 1;"

# 检查 Milvus
python check_milvus.py

# 检查 Redis
docker exec -it affinity-redis redis-cli PING
```

**解决方案**:
```bash
# 重启数据库服务
docker-compose restart postgres neo4j milvus redis

# 检查数据卷
docker volume ls | grep affinity
```

### 问题 4: 内容抓取失败

**症状**: 内容推荐或表情包无数据

**排查**:
```bash
# 检查 RSSHub 可访问性
curl https://rsshub.app/36kr/news

# 查看 Celery 日志
docker-compose logs -f celery-worker | grep "content\|meme"

# 手动触发测试
docker exec affinity-celery-worker celery -A app.worker call \
  app.worker.tasks.content_aggregation.test_fetch_content
```

**解决方案**:
- 检查网络连接
- 如果 RSSHub 不可用，可以自建 RSSHub 实例
- 配置微博官方 API（可选）

---

## 性能优化建议

### 1. 数据库优化

```sql
-- 为常用查询创建索引
CREATE INDEX IF NOT EXISTS idx_memories_user_status ON memories(user_id, status);
CREATE INDEX IF NOT EXISTS idx_memories_created_at ON memories(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_affinity_user ON affinity_history(user_id, created_at DESC);
```

### 2. Redis 缓存配置

```env
# 增加 Redis 内存限制
REDIS_MAXMEMORY=2gb
REDIS_MAXMEMORY_POLICY=allkeys-lru
```

### 3. Celery 并发配置

```bash
# 增加 Worker 并发数（根据 CPU 核心数）
docker-compose up -d --scale celery-worker=4
```

### 4. Milvus 性能调优

```yaml
# docker-compose.yml 中增加 Milvus 内存
milvus:
  environment:
    - MILVUS_CACHE_SIZE=4GB
```

---

## 监控和日志

### 查看实时日志

```bash
# 所有服务
docker-compose logs -f

# 特定服务
docker-compose logs -f api
docker-compose logs -f celery-worker

# 过滤关键词
docker-compose logs -f | grep "ERROR\|WARNING"
```

### Prometheus 指标

访问 http://localhost:8000/metrics 查看 Prometheus 指标

### Grafana 仪表板

1. 访问 http://localhost:3000
2. 导入 `monitoring/grafana/dashboards/affinity.json`
3. 配置 Prometheus 数据源

---

## 备份和恢复

### 备份数据

```bash
# 备份 PostgreSQL
docker exec affinity-postgres pg_dump -U affinity affinity > backup_postgres_$(date +%Y%m%d).sql

# 备份 Neo4j
docker exec affinity-neo4j neo4j-admin dump --database=neo4j --to=/backups/neo4j_$(date +%Y%m%d).dump

# 备份 Milvus
# Milvus 数据存储在 Docker 卷中
docker run --rm -v affinity_milvus_data:/data -v $(pwd):/backup alpine tar czf /backup/milvus_backup_$(date +%Y%m%d).tar.gz /data
```

### 恢复数据

```bash
# 恢复 PostgreSQL
docker exec -i affinity-postgres psql -U affinity affinity < backup_postgres_20260119.sql

# 恢复 Neo4j
docker exec affinity-neo4j neo4j-admin load --from=/backups/neo4j_20260119.dump --database=neo4j --force

# 恢复 Milvus
docker run --rm -v affinity_milvus_data:/data -v $(pwd):/backup alpine tar xzf /backup/milvus_backup_20260119.tar.gz -C /
```

---

## 扩展部署

### 水平扩展

```bash
# 增加 API 实例
docker-compose up -d --scale api=3

# 增加 Celery Worker 实例
docker-compose up -d --scale celery-worker=5

# 配置 Nginx 负载均衡
# 参考 nginx.conf 示例
```

### 高可用部署

1. **PostgreSQL 主从复制**
2. **Neo4j 集群模式**
3. **Milvus 分布式部署**
4. **Redis Sentinel 或 Cluster**

---

## 安全加固

### 1. 修改默认密码

```bash
# PostgreSQL
ALTER USER affinity WITH PASSWORD 'new_strong_password';

# Neo4j
docker exec -it affinity-neo4j cypher-shell -u neo4j -p old_password
CALL dbms.security.changePassword('new_strong_password');
```

### 2. 启用 HTTPS

```bash
# 使用 Let's Encrypt
certbot certonly --standalone -d your-domain.com

# 配置 Nginx
# 参考 nginx-ssl.conf 示例
```

### 3. 限制网络访问

```yaml
# docker-compose.yml
services:
  postgres:
    networks:
      - internal  # 不暴露到外网
  
  api:
    networks:
      - internal
      - external  # 只有 API 暴露
```

---

## 下一步

1. **配置域名和 HTTPS**
2. **设置定时备份**
3. **配置监控告警**
4. **优化性能参数**
5. **配置 CDN（可选）**

---

**部署完成！** 🎉

现在你可以开始使用 Affinity 系统了。如有问题，请查看日志或联系技术支持。
