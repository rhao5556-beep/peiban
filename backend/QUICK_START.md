# 🚀 快速开始指南

**5 分钟启动你的 AI 陪伴系统**

---

## ✅ 前置条件

- ✅ Docker 服务已运行
- ✅ 数据库迁移已完成
- ✅ 内容聚合已完成

---

## 🎯 启动步骤

### 1. 启动后端（如果未运行）
```bash
cd backend
docker-compose up -d
```

### 2. 启动前端
```bash
cd frontend
npm run dev
```

### 3. 访问应用
打开浏览器: **http://localhost:5173**

---

## 🧪 快速测试

### 测试冲突解决
在对话中输入:
1. "我喜欢咖啡"
2. "我不喜欢咖啡"
3. 观察系统检测冲突

### 测试内容推荐
1. 点击"内容推荐"标签页
2. 查看 38 条推荐内容
3. 点击"查看详情"
4. 测试反馈按钮

### 测试主动消息
1. 等待 30 秒
2. 观察主动消息弹窗
3. 点击右上角设置图标
4. 测试偏好设置

### 测试表情包
1. 在对话中发送消息
2. 观察 AI 回复（可能包含表情包）
3. 点击表情包反馈按钮
4. 在"内容推荐"页面测试表情包设置

---

## 🔧 常用命令

### 查看服务状态
```bash
cd backend
docker-compose ps
```

### 查看 API 日志
```bash
docker-compose logs -f api
```

### 查看 Celery 日志
```bash
docker-compose logs -f celery-worker
```

### 重启服务
```bash
docker-compose restart api
docker-compose restart celery-worker
```

### 查看数据库数据
```bash
# 内容推荐
docker exec affinity-postgres psql -U affinity -d affinity -c "SELECT COUNT(*) FROM content_library;"

# 表情包
docker exec affinity-postgres psql -U affinity -d affinity -c "SELECT COUNT(*) FROM memes;"

# 主动消息
docker exec affinity-postgres psql -U affinity -d affinity -c "SELECT COUNT(*) FROM proactive_messages;"
```

### 手动触发聚合任务
```bash
# 内容推荐
docker exec affinity-celery-worker celery -A app.worker call app.worker.tasks.content_aggregation.aggregate_content

# 表情包
docker exec affinity-celery-worker celery -A app.worker call app.worker.tasks.meme_aggregation.aggregate_trending_memes
```

### 创建测试主动消息
```bash
docker exec affinity-postgres psql -U affinity -d affinity -c "
INSERT INTO proactive_messages (user_id, trigger_type, content, scheduled_at, status) 
VALUES ((SELECT id FROM users LIMIT 1), 'test', '测试消息', NOW(), 'pending');"
```

---

## 📚 详细文档

- **FINAL_DEPLOYMENT_SUMMARY.md** - 完整部署总结
- **DEPLOYMENT_COMPLETE.md** - 详细部署报告
- **SYSTEMS_STATUS_REPORT.md** - 系统状态报告

---

## 🆘 遇到问题？

### 前端无法连接后端
```bash
# 检查后端是否运行
docker-compose ps

# 测试 API
curl http://localhost:8000/docs
```

### 内容推荐为空
```bash
# 重新运行聚合任务
docker exec affinity-celery-worker celery -A app.worker call app.worker.tasks.content_aggregation.aggregate_content
```

### 主动消息不显示
```bash
# 创建测试消息（见上方"创建测试主动消息"）
```

---

**开始使用吧！** 🎉
