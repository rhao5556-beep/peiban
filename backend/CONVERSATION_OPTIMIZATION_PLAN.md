# 对话质量优化方案

## 问题诊断

你的系统虽然使用了 DeepSeek-V3 这样强大的 LLM，但回复质量不佳的原因：

### 1. Prompt 工程问题 ⭐⭐⭐⭐⭐ (最关键)

**当前问题**：
- Prompt 过于复杂，包含太多结构化数据
- 规则太多太死板，限制了 LLM 的自然表达
- 缺少 Few-shot 示例
- 检索结果呈现不自然（实体-关系 vs 自然语言）

**影响**：
- LLM 看到的是"数据库查询结果"而不是"对话上下文"
- 导致回复生硬、机械、不连贯
- 无法理解用户的潜台词和不完整表达

**解决方案**：
```python
# 改进前（当前）
=== 长期记忆（图谱推理结果）===
- Entity: 二丫 (Person, confidence=0.9)
- Relation: USER -[FRIEND_OF]-> 二丫 (weight=0.8)
- Entity: 沈阳 (Location, confidence=0.85)
- Relation: USER -[VISITED]-> 沈阳 (weight=0.7)

# 改进后
你对用户的了解：
- 二丫是你的朋友
- 你和二丫一起去过沈阳旅游
- 昊哥和张sir是你的朋友，但他们没有去沈阳
```

### 2. 上下文窗口利用不足 ⭐⭐⭐⭐

**当前问题**：
- DeepSeek-V3 有 64K 上下文窗口
- 你只用了约 2K（最近5轮对话 + Top-10检索结果）
- 大量有用信息被丢弃

**解决方案**：
- 增加对话历史到 20-30 轮
- 增加检索结果到 Top-20
- 添加用户画像摘要（从图谱生成）

### 3. 检索质量问题 ⭐⭐⭐

**当前问题**：
- 向量检索可能召回不相关的内容
- 图谱检索只返回直接关系，缺少推理链
- 没有对检索结果进行质量过滤

**解决方案**：
- 改进 Re-rank 算法（考虑语义相关性 + 时间衰减 + 好感度）
- 增加图谱多跳推理（2-hop, 3-hop）
- 添加检索结果置信度过滤

### 4. 缺少对话策略 ⭐⭐⭐

**当前问题**：
- 没有主动澄清机制（用户说话不完整时）
- 没有记忆确认机制（不确定时主动询问）
- 缺少情感共鸣策略

**解决方案**：
- 添加澄清 Prompt："如果用户的问题不够明确，主动询问细节"
- 添加记忆确认："如果不确定，说'我记得你提到过...，是这样吗？'"
- 增强情感响应："识别用户情绪，给予恰当的情感回应"

---

## 立即可实施的改进（按优先级）

### 🔥 优先级 1：优化 Prompt（立即见效，工作量小）

**文件**：`backend/app/services/conversation_service.py`

**修改位置**：`_generate_reply()` 方法，第 892-950 行

**改进内容**：

1. **简化 Prompt 结构**
```python
# 当前（复杂）
prompt = f"""你是一个情感陪伴 AI，名叫 Affinity。

当前用户状态:
- 好感度: {affinity.new_score:.2f} ({affinity.state})
- 情绪: {emotion.get('primary_emotion', 'neutral')}
...（一大堆规则）
"""

# 改进后（简洁）
prompt = f"""你是 Affinity，一个温暖、善解人意的 AI 陪伴助手。

你对用户的了解：
{_format_memories_naturally(memories, graph_facts)}

最近的对话：
{_format_history_naturally(conversation_history)}

用户: {message}

请自然、真诚地回复。{tone_hint}
"""
```

2. **添加 Few-shot 示例**
```python
prompt += """
---
示例对话（参考风格）：

用户: 我和二丫去沈阳溜达过一圈 但是昊哥和张sir没去
Affinity: 听起来那次沈阳之行应该挺有趣的！二丫和你一起肯定玩得很开心。昊哥和张sir下次有机会也会想去看看吧。

用户: 谁去沈阳旅游过
Affinity: 根据你之前告诉我的，你和二丫一起去过沈阳旅游。那次是你们两个人的行程，昊哥和张sir没有参加。
---
"""
```

3. **自然语言化检索结果**
```python
def _format_memories_naturally(memories, graph_facts):
    """将结构化数据转换为自然语言"""
    context = []
    
    # 处理图谱事实
    for fact in graph_facts:
        if fact['relation_type'] == 'FRIEND_OF':
            context.append(f"{fact['entity_name']}是你的朋友")
        elif fact['relation_type'] == 'VISITED':
            context.append(f"你去过{fact['target_name']}")
    
    # 处理对话记忆
    for mem in memories[:3]:
        context.append(f"你之前提到：{mem['content']}")
    
    return "\n".join(context)
```

**预期效果**：
- 回复更自然、流畅
- 能理解不完整的表达
- 减少"机械感"

---

### 🔥 优先级 2：增加上下文窗口利用（中等工作量）

**文件**：`backend/app/services/conversation_service.py`

**修改位置**：
- 第 640 行：`conversation_history = await self._get_conversation_history(session_id, limit=5)`
- 第 662 行：`top_k=10`

**改进内容**：

```python
# 改进前
conversation_history = await self._get_conversation_history(session_id, limit=5)
ranked_memories, ranked_facts = self.retrieval_service.unified_rerank(..., top_k=10)

# 改进后
conversation_history = await self._get_conversation_history(session_id, limit=20)
ranked_memories, ranked_facts = self.retrieval_service.unified_rerank(..., top_k=20)
```

**预期效果**：
- 更好地理解对话上下文
- 减少"我不记得"的情况
- 提升连贯性

---

### 🔥 优先级 3：改进检索策略（较大工作量）

**文件**：`backend/app/services/retrieval_service.py`

**改进内容**：

1. **增加语义相似度阈值过滤**
```python
def unified_rerank(self, vector_memories, graph_facts, affinity_score, top_k=10):
    # 过滤低相关性结果
    filtered_memories = [
        m for m in vector_memories 
        if m.get('similarity_score', 0) > 0.5  # 阈值
    ]
    
    # 继续 re-rank...
```

2. **增加图谱多跳推理**
```python
async def retrieve_entity_facts(self, user_id, message, graph_service):
    # 当前：只查询1跳关系
    # 改进：查询2跳关系
    
    query = """
    MATCH (u:User {id: $user_id})-[r1]-(e1)-[r2]-(e2)
    WHERE e1.name IN $entities
    RETURN e1, r1, e2, r2
    LIMIT 20
    """
```

3. **添加时间衰减权重**
```python
def calculate_relevance_score(memory, affinity_score, current_time):
    # 基础相似度
    base_score = memory['similarity_score']
    
    # 时间衰减（越新越重要）
    days_ago = (current_time - memory['created_at']).days
    time_decay = math.exp(-0.1 * days_ago)
    
    # 好感度加权
    affinity_boost = 1.0 + (affinity_score - 0.5) * 0.5
    
    return base_score * time_decay * affinity_boost
```

---

### 🔥 优先级 4：添加对话策略（中等工作量）

**改进内容**：

1. **主动澄清机制**
```python
prompt += """
如果用户的问题不够明确或有歧义，请主动询问细节。

示例：
用户: 谁去过
Affinity: 你是想问谁去过哪里吗？我记得你提到过几次旅行，比如沈阳、丹东等地方。
```

2. **记忆确认机制**
```python
prompt += """
如果不完全确定某个信息，可以用"我记得你提到过..."的方式确认。

示例：
用户: 我表妹叫什么
Affinity: 我记得你提到过二丫，她是你的表妹对吗？
```

3. **情感共鸣**
```python
# 在 Prompt 中添加情感响应指导
if emotion['valence'] < -0.3:
    prompt += "\n用户情绪不佳，给予温暖的安慰和支持。"
elif emotion['valence'] > 0.3:
    prompt += "\n用户情绪积极，分享他们的快乐。"
```

---

## 对比：豆包/ChatGPT vs 你的系统

### 豆包/ChatGPT 的优势

1. **Prompt 工程成熟**
   - 经过大量 A/B 测试优化
   - Few-shot 示例精心设计
   - 规则简洁但有效

2. **上下文管理优秀**
   - 智能压缩对话历史
   - 动态调整上下文窗口
   - 保留关键信息

3. **对话策略完善**
   - 主动澄清
   - 记忆确认
   - 情感共鸣
   - 话题引导

4. **模型微调**
   - 针对对话场景微调
   - RLHF 优化
   - 安全性过滤

### 你的系统可以达到的水平

通过上述优化，你的系统可以达到：

✅ **理解能力**：接近豆包/ChatGPT（因为用的是同级别的 LLM）
✅ **记忆能力**：超过豆包/ChatGPT（你有图谱 + 向量双重记忆）
✅ **个性化**：超过豆包/ChatGPT（你有好感度系统）
⚠️ **自然度**：需要优化 Prompt 才能接近
⚠️ **连贯性**：需要增加上下文窗口

---

## 实施建议

### 第一周：快速见效（Prompt 优化）

1. 实施优先级 1 的 Prompt 优化
2. 添加 Few-shot 示例
3. 自然语言化检索结果
4. 测试并调整

**预期提升**：回复质量提升 50%

### 第二周：深度优化（检索 + 上下文）

1. 增加上下文窗口（优先级 2）
2. 改进检索策略（优先级 3）
3. 添加对话策略（优先级 4）

**预期提升**：回复质量再提升 30%

### 第三周：精细调优

1. A/B 测试不同 Prompt 版本
2. 调整检索参数（top_k, 阈值等）
3. 优化 Re-rank 算法
4. 收集用户反馈

**预期提升**：回复质量再提升 20%

---

## 总结

你的问题不是 LLM 不够强，而是：

1. **Prompt 工程不够好**（最关键）
2. **上下文窗口利用不足**
3. **检索结果呈现不自然**
4. **缺少对话策略**

通过上述优化，你的系统完全可以达到豆包/ChatGPT 的对话水平，甚至在记忆和个性化方面超越它们！

关键是：**让 LLM 看到的是"自然的对话上下文"，而不是"数据库查询结果"**。
