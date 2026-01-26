# 表情包梗图系统 - 测试验证计划

## 测试目标

验证表情包梗图系统 MVP 的核心功能是否正常工作，包括：
- 数据库架构完整性
- 核心服务功能
- API 端点可用性
- Celery 定时任务调度
- 对话服务集成
- 端到端流程

---

## 测试环境准备

### 前置条件检查

```bash
# 1. 检查所有服务运行状态
docker-compose ps

# 应该看到以下服务状态为 Up:
# - affinity-postgres
# - affinity-redis
# - affinity-neo4j
# - affinity-milvus
# - affinity-api
# - affinity-celery-worker
# - affinity-celery-beat
```

### 环境变量检查

```bash
# 检查表情包系统相关环境变量
cd backend
grep "MEME\|WEIBO" .env

# 应该包含:
# WEIBO_API_KEY=your-key
# WEIBO_API_BASE_URL=https://api.weibo.com/2
# MEME_SAFETY_SCREENING_ENABLED=true
# MEME_SENSOR_INTERVAL_HOURS=1
# MEME_TREND_UPDATE_INTERVAL_HOURS=2
# MEME_ARCHIVAL_DECLINING_DAYS=30
# MEME_DUPLICATE_CHECK_ENABLED=true
```

---

## 第一阶段：数据库验证

### 1.1 验证表已创建

```bash
docker exec -it affinity-postgres psql -U affinity -d affinity -c "\dt meme*"
```

**预期输出：**
```
                    List of relations
 Schema |          Name           | Type  |  Owner   
--------+-------------------------+-------+----------
 public | meme_usage_history      | table | affinity
 public | memes                   | table | affinity
 public | user_meme_preferences   | table | affinity
```

### 1.2 验证表结构

```bash
# 检查 memes 表
docker exec -it affinity-postgres psql -U affinity -d affinity -c "\d memes"

# 检查 meme_usage_history 表
docker exec -it affinity-postgres psql -U affinity -d affinity -c "\d meme_usage_history"

# 检查 user_meme_preferences 表
docker exec -it affinity-postgres psql -U affinity -d affinity -c "\d user_meme_preferences"
```

**验证要点：**
- memes 表包含 content_hash 字段（唯一索引）
- 所有必需字段存在
- 索引已创建

### 1.3 验证索引

```bash
docker exec -it affinity-postgres psql -U affinity -d affinity -c "
SELECT indexname, indexdef 
FROM pg_indexes 
WHERE tablename IN ('memes', 'meme_usage_history', 'user_meme_preferences')
ORDER BY tablename, indexname;
"
```

**预期索引：**
- idx_meme_status_trend
- idx_meme_safety_status
- idx_meme_trend_score
- idx_meme_content_hash (UNIQUE)
- idx_usage_user_time
- idx_usage_meme

---

## 第二阶段：Celery 任务验证

### 2.1 验证任务注册

```bash
docker exec affinity-celery-worker celery -A app.worker inspect registered | grep meme
```

**预期输出：**
```
app.worker.tasks.meme_aggregation.aggregate_trending_memes
app.worker.tasks.meme_aggregation.update_meme_scores
app.worker.tasks.meme_aggregation.archive_old_memes
```

### 2.2 验证 Celery Beat 调度

```bash
docker exec affinity-celery-beat celery -A app.worker inspect scheduled
```

**预期输出：** 应该看到三个表情包任务的调度信息

### 2.3 手动触发内容聚合任务

```bash
# 触发内容聚合
docker exec affinity-celery-worker celery -A app.worker call meme.aggregate_trending_memes

# 查看任务日志
docker-compose logs celery-worker | grep -A 20 "aggregate_trending_memes"
```

**验证要点：**
- 任务成功执行
- 无错误日志
- 如果微博 API 配置正确，应该看到内容抓取日志

### 2.4 检查数据库中的表情包

```bash
docker exec -it affinity-postgres psql -U affinity -d affinity -c "
SELECT 
    id, 
    text_description, 
    source_platform, 
    status, 
    safety_status, 
    trend_level, 
    trend_score 
FROM memes 
LIMIT 5;
"
```

**预期结果：**
- 如果微博 API 正常，应该有数据
- 如果 API 未配置或失败，表为空（正常）

---

## 第三阶段：API 端点验证

### 3.1 准备测试用户和 Token

```bash
# 创建测试用户（如果不存在）
curl -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "username": "meme_test_user",
    "email": "meme_test@example.com",
    "password": "testpass123"
  }'

# 登录获取 token
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "username": "meme_test_user",
    "password": "testpass123"
  }' | jq -r '.access_token')

echo "Token: $TOKEN"
```

### 3.2 测试 GET /api/v1/memes/trending

```bash
curl -X GET "http://localhost:8000/api/v1/memes/trending?limit=10" \
  -H "Authorization: Bearer $TOKEN" | jq
```

**预期输出：**
```json
{
  "memes": [],
  "total": 0
}
```
或者如果有数据：
```json
{
  "memes": [
    {
      "id": "uuid",
      "image_url": null,
      "text_description": "...",
      "source_platform": "weibo",
      "category": "humor",
      "trend_score": 85.5,
      "trend_level": "hot",
      "usage_count": 0
    }
  ],
  "total": 1
}
```

### 3.3 测试 GET /api/v1/memes/stats

```bash
curl -X GET "http://localhost:8000/api/v1/memes/stats" \
  -H "Authorization: Bearer $TOKEN" | jq
```

**预期输出：**
```json
{
  "total_memes": 0,
  "approved_memes": 0,
  "trending_memes": 0,
  "acceptance_rate": 0.0,
  "avg_trend_score": 0.0
}
```

### 3.4 测试 GET /api/v1/memes/preferences

```bash
curl -X GET "http://localhost:8000/api/v1/memes/preferences" \
  -H "Authorization: Bearer $TOKEN" | jq
```

**预期输出：**
```json
{
  "user_id": "uuid",
  "meme_enabled": true,
  "created_at": "2026-01-18T...",
  "updated_at": "2026-01-18T..."
}
```

### 3.5 测试 PUT /api/v1/memes/preferences

```bash
# 禁用表情包
curl -X PUT "http://localhost:8000/api/v1/memes/preferences?meme_enabled=false" \
  -H "Authorization: Bearer $TOKEN" | jq

# 验证已禁用
curl -X GET "http://localhost:8000/api/v1/memes/preferences" \
  -H "Authorization: Bearer $TOKEN" | jq '.meme_enabled'

# 重新启用
curl -X PUT "http://localhost:8000/api/v1/memes/preferences?meme_enabled=true" \
  -H "Authorization: Bearer $TOKEN" | jq
```

**预期结果：** meme_enabled 值正确更新

---

## 第四阶段：核心服务单元测试

### 4.1 测试安全筛选服务

```bash
cd backend
python test_safety_screener.py
```

**预期输出：** 所有测试通过

### 4.2 测试使用历史服务

```bash
python test_meme_usage_history_service.py
```

**预期输出：** 所有测试通过

---

## 第五阶段：对话服务集成测试

### 5.1 准备测试环境

```bash
# 确保测试用户有足够的好感度（>= 21）
# 可以通过多次对话或直接更新数据库

# 查看当前好感度
curl -X GET "http://localhost:8000/api/v1/affinity/history" \
  -H "Authorization: Bearer $TOKEN" | jq '.[-1].new_score'
```

### 5.2 测试对话中的表情包使用

```bash
# 发送对话消息
curl -X POST "http://localhost:8000/api/v1/conversation/send" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "今天天气真好！",
    "session_id": "meme-test-session"
  }' | jq
```

**验证要点：**
- 响应成功返回
- 如果好感度足够且有合适表情包，响应可能包含表情包字段
- 如果没有表情包，返回纯文本响应（正常）

### 5.3 检查使用历史

```bash
docker exec -it affinity-postgres psql -U affinity -d affinity -c "
SELECT 
    mh.id,
    mh.user_id,
    mh.meme_id,
    mh.used_at,
    mh.user_reaction,
    m.text_description
FROM meme_usage_history mh
JOIN memes m ON mh.meme_id = m.id
ORDER BY mh.used_at DESC
LIMIT 5;
"
```

---

## 第六阶段：端到端流程测试

### 6.1 完整流程测试脚本

创建测试脚本 `backend/test_meme_e2e.py`:

```python
"""表情包系统端到端测试"""
import asyncio
import sys
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.services.content_pool_manager_service import ContentPoolManagerService
from app.services.safety_screener_service import SafetyScreenerService
from app.services.trend_analyzer_service import TrendAnalyzerService
from app.services.usage_decision_engine_service import UsageDecisionEngineService

async def test_e2e():
    """端到端测试"""
    print("🧪 开始表情包系统端到端测试...\n")
    
    # 创建数据库连接
    engine = create_async_engine(settings.DATABASE_URL)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with async_session() as db:
        # 1. 测试内容池管理
        print("1️⃣ 测试内容池管理服务...")
        pool_manager = ContentPoolManagerService(db)
        
        # 创建测试表情包
        test_meme = await pool_manager.create_meme_candidate(
            text_description="测试表情包",
            source_platform="test",
            initial_popularity_score=50.0,
            content_hash="test_hash_123"
        )
        print(f"   ✅ 创建候选表情包: {test_meme.id}")
        
        # 2. 测试安全筛选
        print("\n2️⃣ 测试安全筛选服务...")
        safety_screener = SafetyScreenerService()
        
        result = await safety_screener.screen_meme(test_meme)
        print(f"   ✅ 安全筛选结果: {result.overall_status}")
        
        # 更新状态
        if result.overall_status == "approved":
            await pool_manager.update_meme_status(test_meme.id, "approved", "approved")
            print(f"   ✅ 表情包已批准")
        
        # 3. 测试趋势分析
        print("\n3️⃣ 测试趋势分析服务...")
        trend_analyzer = TrendAnalyzerService(db)
        
        trend_score = await trend_analyzer.calculate_trend_score(test_meme)
        trend_level = trend_analyzer.determine_trend_level(trend_score)
        print(f"   ✅ 趋势分数: {trend_score}, 等级: {trend_level}")
        
        # 4. 测试使用决策引擎
        print("\n4️⃣ 测试使用决策引擎...")
        decision_engine = UsageDecisionEngineService(db)
        
        # 模拟用户上下文
        selected_meme = await decision_engine.should_use_meme(
            user_id="test_user_id",
            affinity_score=60.0,  # friend 状态
            conversation_context="今天天气真好",
            emotional_tone="positive"
        )
        
        if selected_meme:
            print(f"   ✅ 选择表情包: {selected_meme.text_description}")
        else:
            print(f"   ℹ️  未选择表情包（正常，可能因为上下文不匹配）")
        
        # 5. 测试统计
        print("\n5️⃣ 测试统计功能...")
        stats = await pool_manager.get_statistics()
        print(f"   ✅ 统计信息:")
        print(f"      - 总表情包数: {stats.get('total_memes', 0)}")
        print(f"      - 已批准: {stats.get('approved_memes', 0)}")
        print(f"      - 平均趋势分数: {stats.get('avg_trend_score', 0):.2f}")
        
        # 清理测试数据
        print("\n🧹 清理测试数据...")
        await db.execute(f"DELETE FROM memes WHERE id = '{test_meme.id}'")
        await db.commit()
        print("   ✅ 测试数据已清理")
    
    await engine.dispose()
    print("\n✅ 端到端测试完成！")

if __name__ == "__main__":
    try:
        asyncio.run(test_e2e())
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
```

运行测试：

```bash
cd backend
python test_meme_e2e.py
```

---

## 第七阶段：性能验证

### 7.1 API 响应时间

```bash
# 测试 trending 端点响应时间
time curl -X GET "http://localhost:8000/api/v1/memes/trending" \
  -H "Authorization: Bearer $TOKEN" -o /dev/null -s

# 预期: < 500ms
```

### 7.2 Celery 任务执行时间

```bash
# 查看任务执行日志
docker-compose logs celery-worker | grep "Task.*succeeded" | grep meme
```

**预期：**
- aggregate_trending_memes: < 5 分钟
- update_meme_scores: < 30 秒
- archive_old_memes: < 10 秒

---

## 第八阶段：业务规则验证

### 8.1 好感度过滤规则

测试不同好感度等级的表情包使用：

```python
# 创建测试脚本 test_affinity_rules.py
"""测试好感度过滤规则"""
import asyncio
from app.services.usage_decision_engine_service import UsageDecisionEngineService

async def test_affinity_rules():
    # 测试不同好感度等级
    test_cases = [
        (10, "stranger", False),      # 0-20: 不使用
        (30, "acquaintance", True),   # 21-50: 低概率
        (65, "friend", True),         # 51-80: 中概率
        (90, "close_friend", True),   # 81-100: 高概率
    ]
    
    for score, level, should_use in test_cases:
        print(f"测试好感度 {score} ({level})...")
        # 测试逻辑...

asyncio.run(test_affinity_rules())
```

### 8.2 重复使用防止

```bash
# 检查 24 小时内不重复使用
docker exec -it affinity-postgres psql -U affinity -d affinity -c "
SELECT 
    meme_id,
    COUNT(*) as usage_count,
    MAX(used_at) as last_used
FROM meme_usage_history
WHERE used_at >= NOW() - INTERVAL '24 hours'
GROUP BY meme_id
HAVING COUNT(*) > 1;
"
```

**预期：** 应该没有结果（24小时内不重复）

---

## 测试结果汇总

### 测试检查清单

- [ ] 数据库表已创建
- [ ] 数据库索引已创建
- [ ] Celery 任务已注册
- [ ] Celery Beat 调度正常
- [ ] 内容聚合任务可执行
- [ ] API 端点 /trending 正常
- [ ] API 端点 /stats 正常
- [ ] API 端点 /preferences GET 正常
- [ ] API 端点 /preferences PUT 正常
- [ ] API 端点 /feedback 正常
- [ ] 安全筛选服务正常
- [ ] 趋势分析服务正常
- [ ] 使用决策引擎正常
- [ ] 对话服务集成正常
- [ ] 端到端流程正常
- [ ] API 响应时间 < 500ms
- [ ] 好感度过滤规则正确
- [ ] 24小时重复防止正确

### 测试通过率

**通过项数：** _____ / 18

### 发现的问题

1. 
2. 
3. 

### 改进建议

1. 
2. 
3. 

---

## 下一步行动

根据测试结果：

- [ ] **全部通过** → 标记任务 19 完成，进入任务 20 最终验证
- [ ] **部分失败** → 修复问题后重新测试
- [ ] **大部分失败** → 检查环境配置和服务状态

---

## 附录：常见问题排查

### 问题 1: 表未创建

**解决方案：**
```bash
# 重新运行迁移脚本
docker exec -i affinity-postgres psql -U affinity -d affinity < backend/scripts/migrations/add_meme_emoji_system.sql
```

### 问题 2: Celery 任务未注册

**解决方案：**
```bash
# 重启 Celery worker
docker-compose restart celery-worker celery-beat
```

### 问题 3: API 返回 401 未授权

**解决方案：**
```bash
# 重新获取 token
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "meme_test_user", "password": "testpass123"}' \
  | jq -r '.access_token')
```

### 问题 4: 微博 API 调用失败

**解决方案：**
- 检查 WEIBO_API_KEY 是否正确
- 检查网络连接
- 查看 Celery 日志获取详细错误信息

---

**测试执行日期：** __________  
**测试执行人：** __________  
**测试结果：** [ ] 通过  [ ] 部分通过  [ ] 失败
