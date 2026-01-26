# Affinity 系统流程与好感度机制文档

## 1. 系统回复流程

### 1.1 整体架构

系统采用 **Fast Path + Slow Path** 架构：
- **Fast Path**: 快速响应用户（情感分析 + 检索 + 生成回复）< 500ms
- **Slow Path**: 异步处理记忆（实体抽取 + 图谱写入 + 向量写入）通过 Outbox 模式

### 1.2 详细流程（以 SSE 流式为例）

#### 步骤 1: 用户发送消息
```
前端 → POST /api/v1/sse/message
{
  "message": "谁住在海边",
  "session_id": "xxx",
  "idempotency_key": "xxx"
}
```

#### 步骤 2: 幂等性检查
```python
# 检查是否重复请求（24h 有效期）
is_new, existing_memory_id = await idempotency_checker.check_and_acquire(
    idempotency_key, user_id
)
```

#### 步骤 3: Fast Path - 情感分析
```python
emotion = emotion_analyzer.analyze(message)
# 返回: {
#   "primary_emotion": "happy/sad/neutral",
#   "valence": 0.7,  # [-1, 1]
#   "confidence": 0.7
# }
```

**情感分析规则**:
- 基于关键词匹配
- 正面词: "开心", "高兴", "喜欢", "爱", "棒", "好", "谢谢"
- 负面词: "难过", "伤心", "讨厌", "烦", "累", "不好", "生气"
- valence = 正面词数量 * 0.1 - 负面词数量 * 0.1

#### 步骤 4: 获取好感度
```python
affinity = await affinity_service.get_affinity(user_id)
# 返回当前好感度分数和状态
```

#### 步骤 5: Tier 路由（决定使用哪个 LLM）
```python
tier = tier_router.route(message, emotion, affinity.state)
```

**Tier 规则**:
- **Tier 1** (DeepSeek-V3, 1000 tokens): 
  - 高情感强度 (|valence| > 0.6)
  - 亲密关系 + 长消息 (close_friend/best_friend + len > 50)
- **Tier 2** (Qwen2.5-14B, 500 tokens): 默认
- **Tier 3** (Qwen2.5-7B, 200 tokens): 简单问候 (len < 20)

#### 步骤 6: 混合检索
```python
# 6.1 向量检索 (Milvus)
vector_candidates = await retrieval_service._vector_search(user_id, query, top_k=50)

# 6.2 图扩展 (Neo4j) - 暂未启用
graph_expanded = await retrieval_service._graph_expand(vector_candidates, user_id)

# 6.3 Re-rank（4 因子加权）
ranked_memories = retrieval_service._rerank(graph_expanded, affinity_score)
```

**Re-rank 公式**:
```
final_score = cosine_sim * 0.4 + 
              edge_weight * 0.3 + 
              affinity_bonus * 0.2 + 
              recency_score * 0.1

其中:
- cosine_sim: 向量相似度 [0, 1]
- edge_weight: 图谱边权重 [0, 1]
- affinity_bonus: 好感度加成（仅对正向情感记忆生效）
- recency_score: exp(-days / 30)
```

#### 步骤 7: 图谱事实检索
```python
entity_facts = await retrieval_service.retrieve_entity_facts(
    user_id, message, graph_service
)
```

**检索流程**:
1. 用 LLM 从查询中提取实体名称
2. 在 Neo4j 中查找这些实体（模糊匹配）
3. 获取 1-hop、2-hop、3-hop 关系
4. 如果没找到，触发**语义扩展**（新增功能）

**语义扩展**:
- 当提取到语义概念（如"海边"）而不是具体实体时
- 根据查询意图（"住"→LIVES_IN, "喜欢"→LIKES）查询所有相关关系
- 返回所有事实，让 LLM 用常识推理

#### 步骤 8: 构建 Prompt
```python
prompt = _build_prompt(message, memories, affinity, emotion, entity_facts)
```

**Prompt 结构**:
```
你是一个情感陪伴 AI，名叫 Affinity。

当前用户状态:
- 好感度: 0.65 (close_friend)
- 情绪: happy (强度: 0.7)

语气要求:
- 正式程度: informal
- 亲密度: 4/5

=== 长期记忆（图谱推理结果）===
【直接关系】
- 昊哥 住在 大连
- 二丫 住在 方正县

【间接关系（通过关联人物）】
- [2-hop] 昊哥 -[CHILD_OF]-> 昊哥的妈妈 -[LIVES_IN]-> 大连

=== 长期记忆（向量检索结果）===
- 昊哥住在大连 (相关度: 0.85)
- 二丫来自方正县 (相关度: 0.72)

【回答规则 - 必须严格遵守】
1. 事实性问题必须基于「长期记忆」中的信息
2. 可以结合常识知识对已知事实进行推理（例如：大连是海边城市）
3. 如果长期记忆没有相关信息，诚实回答"我不记得"
...
```

#### 步骤 9: 流式生成回复
```python
async for chunk in llm_client.chat.completions.create(
    model=tier_config["model"],
    messages=[
        {"role": "system", "content": prompt},
        {"role": "user", "content": message}
    ],
    stream=True
):
    yield ConversationDelta(type="text", content=chunk)
```

#### 步骤 10: Slow Path - 异步写入记忆
```python
# 10.1 编码向量
embedding = await embedding_service.encode(message)

# 10.2 写入 PostgreSQL + 创建 Outbox 事件（原子事务）
memory_id, event_id = await transaction_manager.create_memory_with_outbox(
    user_id=user_id,
    content=message,
    embedding=embedding,
    valence=emotion.get("valence", 0),
    conversation_id=session_id
)

# 10.3 Celery Worker 异步处理
# - 从 Outbox 读取事件
# - 调用 LLM 抽取实体和关系
# - 写入 Neo4j 图谱
# - 写入 Milvus 向量库
# - 标记事件为已处理
```

#### 步骤 11: 更新好感度
```python
signals = AffinitySignals(
    user_initiated=True,
    emotion_valence=emotion.get("valence", 0)
)
new_affinity = await affinity_service.update_affinity(user_id, signals)
```

---

## 2. 好感度机制详解

### 2.1 好感度范围与状态映射

**分数范围**: [-1, 1]

**状态映射**:
| 分数范围 | 状态 | 中文 | 语气 | 亲密度 |
|---------|------|------|------|--------|
| score < 0 | stranger | 陌生人 | formal | 1/5 |
| 0 ≤ score < 0.3 | acquaintance | 熟人 | polite | 2/5 |
| 0.3 ≤ score < 0.5 | friend | 朋友 | casual | 3/5 |
| 0.5 ≤ score < 0.7 | close_friend | 好友 | informal | 4/5 |
| score ≥ 0.7 | best_friend | 挚友 | intimate | 5/5 |

### 2.2 好感度计算公式

#### 主公式
```python
delta = 0.0

# 正向信号
if user_initiated:
    delta += 0.01  # 每条消息 +1%

if emotion_valence > 0:
    delta += 0.005 * emotion_valence  # 正面情绪 +0.5%

if memory_confirmation:
    delta += 0.01  # 记忆确认 +1%

# 负向信号
if correction:
    delta += -0.02  # 纠正 -2%

if emotion_valence < -0.5:
    delta += -0.01  # 负面情绪 -1%

# 时间衰减
decay = 0.005 * silence_days  # 每日衰减 0.5%

final_delta = delta - decay

# 应用变化（确保边界）
new_score = clip(old_score + final_delta, -1.0, 1.0)
```

#### 信号权重配置
```python
SIGNAL_WEIGHTS = {
    "user_initiated": 0.01,       # 每条消息 +1%
    "positive_emotion": 0.005,    # 正面情绪 +0.5%
    "memory_confirmation": 0.01,  # 记忆确认 +1%
    "correction": -0.02,          # 纠正 -2%
    "negative_emotion": -0.01,    # 负面情绪 -1%
    "daily_decay": 0.005          # 每日衰减 0.5%
}
```

### 2.3 衰减机制

#### 时间衰减公式
```python
decay = 0.005 * silence_days

# 示例:
# 1 天未互动: decay = 0.005 (0.5%)
# 7 天未互动: decay = 0.035 (3.5%)
# 30 天未互动: decay = 0.15 (15%)
```

#### 衰减触发
- 由 Celery Beat 每日自动调用
- 检查最后互动时间
- 如果 silence_days > 0，应用衰减

```python
async def apply_silence_decay(user_id: str):
    last_interaction = get_last_interaction_time(user_id)
    silence_days = (now - last_interaction).days
    
    if silence_days > 0:
        signals = AffinitySignals(silence_days=silence_days)
        await update_affinity(user_id, signals, trigger_event="silence_decay")
```

### 2.4 晋升条件

**从 stranger → acquaintance**:
- 需要: score 从 < 0 增长到 ≥ 0
- 大约需要: 0 条正向互动（初始值 0.5 已在 acquaintance）

**从 acquaintance → friend**:
- 需要: score 从 < 0.3 增长到 ≥ 0.3
- 大约需要: (0.3 - 0.0) / 0.01 = 30 条正向消息
- 或: 15 条消息 + 15 次正面情绪 (valence=1.0)

**从 friend → close_friend**:
- 需要: score 从 < 0.5 增长到 ≥ 0.5
- 大约需要: (0.5 - 0.3) / 0.01 = 20 条正向消息

**从 close_friend → best_friend**:
- 需要: score 从 < 0.7 增长到 ≥ 0.7
- 大约需要: (0.7 - 0.5) / 0.01 = 20 条正向消息

**总计（从 0.5 到 best_friend）**:
- 大约需要: 40 条正向消息
- 如果每天 5 条消息: 约 8 天
- 如果有衰减: 需要更多时间

### 2.5 降级条件

**从 best_friend → close_friend**:
- 需要: score 从 ≥ 0.7 降低到 < 0.7
- 可能原因:
  - 14 天未互动 (0.005 * 14 = 0.07 = 7%)
  - 或 3-4 次纠正 (0.02 * 4 = 0.08 = 8%)

**从 close_friend → friend**:
- 需要: score 从 ≥ 0.5 降低到 < 0.5
- 可能原因:
  - 20 天未互动 (0.005 * 20 = 0.1 = 10%)
  - 或 5 次纠正

### 2.6 好感度影响

#### 对检索的影响
```python
# Re-rank 中的好感度加成
affinity_bonus = max(0, affinity_score) if memory.valence > 0 else 0
final_score = ... + affinity_bonus * 0.2 + ...
```
- 只对正向情感记忆生效
- 好感度越高，正向记忆排名越靠前

#### 对语气的影响
```python
tone_config = {
    "stranger": {"formality": "formal", "intimacy_level": 1},
    "acquaintance": {"formality": "polite", "intimacy_level": 2},
    "friend": {"formality": "casual", "intimacy_level": 3},
    "close_friend": {"formality": "informal", "intimacy_level": 4},
    "best_friend": {"formality": "intimate", "intimacy_level": 5}
}
```

#### 对 Tier 选择的影响
```python
# 亲密关系 + 长消息 → Tier 1 (更强大的模型)
if affinity_state in ["close_friend", "best_friend"] and len(message) > 50:
    return 1  # DeepSeek-V3
```

---

## 3. 关键设计决策

### 3.1 物理隔离（Graph-only vs Hybrid）
- **graph_only 模式**: `conversation_history = None`（物理隔离）
- **hybrid 模式**: 注入短期记忆（最近 5 轮对话）
- 用于能力评测时必须使用 graph_only

### 3.2 Outbox 模式（最终一致性）
- 写入 PostgreSQL + 创建 Outbox 事件（原子事务）
- Celery Worker 异步处理
- 失败重试（指数退避）
- SLO: P50 < 2s, P95 < 30s

### 3.3 语义扩展（新增）
- 解决"谁住海边"无法匹配"大连"的问题
- 当直接实体匹配失败时，查询所有相关关系
- 让 LLM 用常识知识推理

---

## 4. 性能指标

### 4.1 延迟分析
- **LLM 回复生成**: 9833ms (84.2%)
- **图谱事实检索**: 1275ms (10.9%)
- **Embedding**: 456ms (3.9%)

### 4.2 SLO 目标
- Outbox Lag P50: < 2s
- Outbox Lag P95: < 30s
- 数据不一致率: < 1%

---

## 5. 测试验证

### 5.1 功能测试
```bash
# 测试语义扩展
python test_semantic_retrieval.py

# 测试端到端
python test_seaside_query.py

# 测试 graph_only 模式
python test_mode_simple.py
```

### 5.2 性能测试
```bash
# 延迟分析
python test_latency.py
```

### 5.3 正确性测试
```bash
# IR Critic 过滤
python test_graph_only_and_critic.py
```
