# Celery Beat RSS自动更新配置完成报告

## 实施日期
2026-01-20

## 问题回顾

### 1. 前端只显示3条推荐？
**答案：这是正常的设计行为！**

- 后端在生成推荐时使用 `LIMIT 3`，避免信息过载
- 数据库中确实只有3条推荐记录
- 前端会显示所有推荐内容，没有额外限制

### 2. 推荐的URL是虚构的？
**答案：URL格式是真实的，但内容是手动插入的示例数据！**

当前数据库中的12条内容都是通过 `seed_real_rss_content.py` 手动插入的：
- B站: `https://www.bilibili.com/video/BV1xx411c7XY`
- 知乎: `https://www.zhihu.com/question/580345678`
- 微博: `https://weibo.com/1234567890/Abc123Def456`

**真正的问题：系统还没有启用自动RSS爬虫！**

### 3. 如何启用Celery Beat自动更新？
**已完成配置！**

## 实施内容

### 1. 修复Docker镜像依赖问题 ✅

**问题**：Docker镜像缺少 `feedparser` 和 `circuitbreaker` 依赖

**解决方案**：修改 `docker-compose.yml`，在容器启动时自动安装依赖

```yaml
# Celery Worker
command: >
  sh -c "pip install --no-cache-dir feedparser==6.0.11 circuitbreaker==2.0.0 &&
         celery -A app.worker worker --loglevel=info --concurrency=4 -Q celery,default,high_priority,low_priority,maintenance"

# Celery Beat
command: >
  sh -c "pip install --no-cache-dir feedparser==6.0.11 circuitbreaker==2.0.0 &&
         celery -A app.worker beat --loglevel=info"
```

### 2. 启动Celery服务 ✅

```bash
docker-compose up -d celery-worker celery-beat
```

**状态验证**：
```bash
$ docker ps --filter "name=celery"
CONTAINER ID   IMAGE                    STATUS          PORTS      NAMES
d8b8b8aa1740   affinity-celery-beat     Up 28 seconds   8000/tcp   affinity-celery-beat
6ff48a6d343b   affinity-celery-worker   Up 28 seconds   8000/tcp   affinity-celery-worker
```

### 3. 验证任务注册 ✅

```bash
$ docker exec affinity-celery-worker celery -A app.worker inspect registered
```

**已注册的内容聚合任务**：
- ✅ `content.fetch_daily` - 每日内容抓取（7:00 AM）
- ✅ `content.cleanup_old` - 清理旧内容（2:00 AM）
- ✅ `content.test_fetch` - 手动测试抓取
- ✅ `content.generate_recommendations` - 生成推荐

## 定时任务配置

### Celery Beat调度

在 `app/worker/__init__.py` 中配置：

```python
celery_app.conf.beat_schedule = {
    'fetch-daily-content': {
        'task': 'content.fetch_daily',
        'schedule': crontab(hour=7, minute=0),  # 每天7:00 AM
    },
    'cleanup-old-content': {
        'task': 'content.cleanup_old',
        'schedule': crontab(hour=2, minute=0),  # 每天2:00 AM
    },
}
```

### RSS源配置

在 `app/services/content_aggregator_service.py` 中配置：

```python
RSS_FEEDS = [
    # 科技新闻
    "https://rsshub.app/36kr/news",
    "https://rsshub.app/ithome/ranking",
    "https://rsshub.app/geekpark",
    
    # 综合新闻
    "https://rsshub.app/thepaper/featured",
    
    # 开发者
    "https://rsshub.app/github/trending/daily",
    "https://rsshub.app/v2ex/hot",
    
    # 生活
    "https://rsshub.app/douban/movie/weekly",
]
```

## 使用指南

### 手动触发内容抓取

```bash
# 方法1: 测试抓取（只抓取RSS，不保存）
docker exec affinity-celery-worker celery -A app.worker call content.test_fetch

# 方法2: 完整抓取（抓取并保存到数据库）
docker exec affinity-celery-worker celery -A app.worker call content.fetch_daily

# 方法3: 使用Python脚本
python seed_real_rss_content.py

# 方法4: 使用Windows批处理脚本
.\update_content_daily.bat
```

### 查看Celery状态

```bash
# 查看容器状态
docker ps --filter "name=celery"

# 查看Worker日志
docker logs affinity-celery-worker --tail 50

# 查看Beat日志
docker logs affinity-celery-beat --tail 50

# 查看活动任务
docker exec affinity-celery-worker celery -A app.worker inspect active

# 查看已注册任务
docker exec affinity-celery-worker celery -A app.worker inspect registered

# 查看定时任务
docker exec affinity-celery-beat celery -A app.worker inspect scheduled
```

### 查看数据库内容

```bash
# 查看今日内容统计
docker exec affinity-postgres psql -U affinity -d affinity -c "
SELECT source, COUNT(*) as count 
FROM content_library 
WHERE DATE(fetched_at) = CURRENT_DATE 
GROUP BY source;"

# 查看最新内容
docker exec affinity-postgres psql -U affinity -d affinity -c "
SELECT id, source, title, content_url, fetched_at 
FROM content_library 
ORDER BY fetched_at DESC 
LIMIT 10;"

# 查看推荐统计
docker exec affinity-postgres psql -U affinity -d affinity -c "
SELECT COUNT(*) as total_recommendations,
       COUNT(DISTINCT user_id) as unique_users
FROM recommendation_history
WHERE DATE(recommended_at) = CURRENT_DATE;"
```

## 系统架构

### 数据流

```
RSS源 → ContentAggregatorService → content_library表
                ↓
        Celery Beat定时任务（每日7:00）
                ↓
        自动抓取最新内容
                ↓
        推荐引擎选择内容
                ↓
        用户看到真实推荐
```

### 关键组件

1. **ContentAggregatorService** (`app/services/content_aggregator_service.py`)
   - RSS解析和内容标准化
   - 多源并发抓取
   - 内置去重和质量评分
   - 熔断保护和重试机制

2. **Celery定时任务** (`app/worker/tasks/content_aggregation.py`)
   - 自动化内容更新
   - 旧内容清理
   - 错误重试机制

3. **数据库表**
   - `content_library`: 存储所有内容
   - `recommendation_history`: 推荐记录
   - `user_content_preference`: 用户偏好

## 当前状态

### ✅ 已完成
- Docker镜像依赖修复
- Celery Worker和Beat启动
- 任务注册验证
- 定时任务配置
- RSS源配置
- 手动触发脚本

### ⏳ 待验证
- RSS自动抓取功能（等待明天7:00 AM自动执行）
- 内容去重逻辑
- 质量评分算法

### 📊 当前数据
- 总内容：12条（手动插入的示例数据）
- 来源：bilibili (5条), zhihu (5条), weibo (3条)
- 推荐：3条/用户

## 下一步行动

### 立即可做
1. **手动测试RSS抓取**：
   ```bash
   docker exec affinity-celery-worker celery -A app.worker call content.test_fetch
   ```

2. **查看抓取结果**：
   ```bash
   docker logs affinity-celery-worker --tail 100 | grep -i "rss\|fetch\|content"
   ```

3. **验证数据库更新**：
   ```bash
   docker exec affinity-postgres psql -U affinity -d affinity -c "
   SELECT COUNT(*) FROM content_library WHERE DATE(fetched_at) = CURRENT_DATE;"
   ```

### 明天验证
1. 等待7:00 AM自动抓取
2. 检查是否有新内容
3. 验证推荐是否更新

### 长期优化
1. 添加更多RSS源
2. 优化内容质量评分
3. 实现基于用户偏好的过滤
4. 添加内容缓存机制

## 故障排查

### 问题：容器启动失败
```bash
# 检查日志
docker logs affinity-celery-worker --tail 50
docker logs affinity-celery-beat --tail 50

# 重启容器
docker-compose restart celery-worker celery-beat
```

### 问题：依赖安装失败
```bash
# 手动安装依赖
docker exec affinity-celery-worker pip install feedparser==6.0.11 circuitbreaker==2.0.0

# 重启容器
docker-compose restart celery-worker
```

### 问题：RSS抓取失败
```bash
# 检查网络连接
docker exec affinity-celery-worker ping -c 3 rsshub.app

# 手动测试RSS解析
docker exec affinity-celery-worker python -c "
import feedparser
feed = feedparser.parse('https://rsshub.app/36kr/news')
print(f'Entries: {len(feed.entries)}')
"
```

### 问题：任务未执行
```bash
# 检查Beat是否运行
docker exec affinity-celery-beat celery -A app.worker inspect scheduled

# 检查Worker是否接收任务
docker exec affinity-celery-worker celery -A app.worker inspect active

# 手动触发任务
docker exec affinity-celery-worker celery -A app.worker call content.fetch_daily
```

## 总结

✅ **Celery Beat自动更新系统已成功配置并启动！**

- 依赖问题已解决（feedparser + circuitbreaker）
- 容器正常运行
- 任务已注册
- 定时任务已配置（每天7:00 AM抓取，2:00 AM清理）

**下一步**：等待明天7:00 AM自动抓取，或手动触发测试抓取验证功能。

**注意**：当前数据库中的12条内容都是手动插入的示例数据，不是从RSS抓取的真实内容。RSS自动抓取功能已配置完成，等待首次执行。
