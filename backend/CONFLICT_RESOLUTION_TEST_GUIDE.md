# 冲突记忆处理 - 测试指南

## 快速测试

### 1. 运行自动化测试

```bash
cd backend
python test_conflict_resolution_short_term.py
```

**预期输出**：
```
✅ 所有测试通过！

短期优化方案已成功实施：
1. ✅ Prompt 增强 - 添加了冲突处理规则和示例
2. ✅ 最新优先重排序 - 最近7天记忆加权 15%
3. ✅ 轻量冲突探测 - 检测 LIKES/DISLIKES 冲突并在 Prompt 中警告
```

---

## 手动测试场景

### 场景 1: 基本冲突检测

**测试步骤**：

1. 启动服务：
```bash
docker-compose up -d
```

2. 在前端（http://localhost:5173）进行对话：

```
用户: 我喜欢茶
AI: [回复]

用户: 我讨厌茶
AI: [回复]

用户: 我是喜欢茶还是讨厌茶？
AI: [应该提及矛盾，优先使用最新观点]
```

**预期 AI 回复**：
> "根据你最近的说法，你是讨厌茶的。不过我注意到你之前说过喜欢茶，想法改变了吗？"

**验证点**：
- ✅ AI 提及了矛盾
- ✅ AI 优先使用最新观点（"讨厌茶"）
- ✅ AI 询问用户澄清

---

### 场景 2: 精确表述优先

**测试步骤**：

```
用户: 我喜欢茶
AI: [回复]

用户: 我讨厌茶
AI: [回复]

用户: 其实我喜欢淡淡的茶，但不喜欢浓茶
AI: [回复]

用户: 我是喜欢茶还是讨厌茶？
AI: [应该使用更精确的表述]
```

**预期 AI 回复**：
> "我记得你说过喜欢淡淡的茶，但不太喜欢浓茶。是这样吗？"

**验证点**：
- ✅ AI 使用了更精确的表述
- ✅ AI 没有简单地说"喜欢"或"讨厌"

---

### 场景 3: 时间加权验证

**测试步骤**：

1. 创建旧记忆（10天前）：
```
用户: 我喜欢咖啡
```

2. 等待几天（或手动修改数据库时间戳）

3. 创建新记忆（今天）：
```
用户: 我讨厌咖啡
```

4. 查询：
```
用户: 我喜欢咖啡吗？
AI: [应该优先使用最新观点]
```

**预期 AI 回复**：
> "根据你最近的说法，你是讨厌咖啡的。"

**验证点**：
- ✅ AI 优先使用最新记忆（最近7天内）
- ✅ 最新记忆获得了 15% 的分数加权

---

## 调试技巧

### 1. 查看日志

```bash
# 查看 API 日志
docker-compose logs -f api

# 查看 Celery Worker 日志
docker-compose logs -f celery-worker
```

**关键日志**：
```
INFO:app.services.conversation_service:Conflict detected: 茶 (LIKES vs DISLIKES)
INFO:app.services.retrieval_service:Recency boost applied: memory from 2 days ago, score 0.750 -> 0.863
```

### 2. 检查 Prompt

在 `conversation_service.py` 中临时添加日志：

```python
def _build_prompt(...):
    # ... 构建 prompt ...
    
    # 临时调试：打印 Prompt
    logger.info(f"Generated Prompt:\n{prompt}")
    
    return prompt
```

**验证点**：
- ✅ Prompt 包含 `【⚠️ 冲突提醒】`
- ✅ Prompt 包含 `【冲突记忆处理规则】`
- ✅ 冲突警告提到了具体的目标（如"茶"）

### 3. 检查重排序结果

在 `retrieval_service.py` 中临时添加日志：

```python
def unified_rerank(...):
    # ... 重排序逻辑 ...
    
    # 临时调试：打印重排序结果
    for i, mem in enumerate(ranked_memories[:5]):
        logger.info(f"Rank {i+1}: {mem.content} (score={mem.final_score:.4f}, created={mem.created_at})")
    
    return ranked_memories, ranked_facts
```

**验证点**：
- ✅ 最近7天的记忆分数更高
- ✅ 分数差异约为 15%

---

## 数据库验证

### 查看记忆数据

```bash
docker exec -it affinity-postgres psql -U affinity -d affinity
```

```sql
-- 查看用户的所有记忆
SELECT id, content, created_at, valence
FROM memories
WHERE user_id = 'your_user_id'
ORDER BY created_at DESC
LIMIT 10;

-- 查看图谱中的 LIKES/DISLIKES 关系
```

### 查看 Neo4j 图谱

```bash
# 访问 Neo4j Browser
# http://localhost:7474
# 用户名: neo4j
# 密码: neo4j_secret
```

```cypher
// 查看用户的所有 LIKES 关系
MATCH (u:User {user_id: 'your_user_id'})-[r:LIKES]->(target)
RETURN u, r, target

// 查看用户的所有 DISLIKES 关系
MATCH (u:User {user_id: 'your_user_id'})-[r:DISLIKES]->(target)
RETURN u, r, target

// 查找冲突：同一个目标既有 LIKES 又有 DISLIKES
MATCH (u:User {user_id: 'your_user_id'})-[r1:LIKES]->(target)<-[r2:DISLIKES]-(u)
RETURN target.name AS target, r1.weight AS like_weight, r2.weight AS dislike_weight
```

---

## 性能测试

### 测试响应时间

```bash
cd backend
python -c "
import asyncio
import time
from app.services.conversation_service import ConversationService

async def test():
    service = ConversationService()
    
    start = time.time()
    response = await service.process_message(
        user_id='test_user',
        message='我是喜欢茶还是讨厌茶',
        session_id='test_session',
        mode='hybrid'
    )
    end = time.time()
    
    print(f'Response time: {(end - start) * 1000:.0f}ms')
    print(f'Reply: {response.reply}')

asyncio.run(test())
"
```

**预期结果**：
- 响应时间增加 < 5ms（可忽略）
- 回复包含冲突处理逻辑

---

## 常见问题

### Q1: 为什么最新的记忆没有排在第一位？

**A**: 可能的原因：
1. 负面情感记忆不获得 `affinity_bonus`，所以分数可能较低
2. 其他因子（cosine_sim, edge_weight）的影响
3. 15% 的加权可能不足以超过其他记忆

**解决方案**：
- 如果需要更强的时间优先，可以增加 `recency_boost` 到 0.20 或 0.25
- 或者在冲突场景下，强制使用最新记忆（需要修改代码）

### Q2: 冲突警告没有出现在 Prompt 中？

**A**: 可能的原因：
1. 图谱中没有 LIKES/DISLIKES 关系（记忆还在 Outbox 队列中）
2. 实体名称不匹配（如"茶"vs"绿茶"）
3. 检索没有返回相关的图谱事实

**解决方案**：
- 等待 Outbox 处理完成（检查 Celery Worker 日志）
- 检查 Neo4j 中是否有对应的关系
- 增加检索的 top_k 数量

### Q3: AI 没有按照冲突处理规则回答？

**A**: 可能的原因：
1. LLM 没有严格遵守 Prompt 指令（模型能力问题）
2. Prompt 太长，关键信息被忽略
3. 使用了弱模型（Tier 3 - 7B）

**解决方案**：
- 确保使用强模型（Tier 1 - DeepSeek-V3）
- 简化 Prompt，突出冲突警告
- 增加 Prompt 中的示例数量

---

## 成功标准

### 最低标准（必须满足）

- ✅ 自动化测试全部通过
- ✅ 冲突场景下，AI 提及矛盾
- ✅ 最近7天的记忆获得加权

### 理想标准（期望满足）

- ✅ AI 主动询问用户澄清
- ✅ AI 优先使用最新观点
- ✅ 回复透明可解释

### 卓越标准（超出预期）

- ✅ AI 能理解更精确的表述
- ✅ AI 能基于上下文推理
- ✅ 用户体验显著提升

---

## 回滚方案

如果优化导致问题，可以快速回滚：

### 1. 回滚 Prompt 增强

```python
# 在 conversation_service.py 中
# 删除或注释掉 "【冲突记忆处理规则】" 部分
```

### 2. 回滚最新优先重排序

```python
# 在 retrieval_service.py 中
# 删除或注释掉 "新增：最新优先加权" 部分
```

### 3. 回滚轻量冲突探测

```python
# 在 conversation_service.py 中
# 删除或注释掉 "新增：轻量冲突探测" 部分
```

---

**最后更新**：2026-01-19
**测试状态**：所有测试通过，可立即上线
