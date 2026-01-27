# LoCoMo 评测改进方案

**当前状态**: 8.36% 准确率（1986 题中仅 166 题正确）  
**目标**: 提升到 40%+ 准确率

---

## 🔴 核心问题分析

### 问题 1: 检索失败率 > 90%

**症状**: 几乎所有回答都是"我没有足够的信息"

**可能原因**:
1. **记忆未存储**: Outbox 事件未处理，记忆未写入 Neo4j/Milvus
2. **检索策略失效**: 查询与记忆的相似度计算失败
3. **上下文窗口太小**: 长对话历史中的早期记忆被遗忘
4. **实体提取失败**: 关键实体未被识别和存储

### 问题 2: 时间理解崩溃（0.62%）

**症状**: 时间相关问题几乎全错

**原因**: 与 KnowMeBench 一致
- 时间实体提取不准确
- 时间格式不标准化
- 缺少时间推理能力

### 问题 3: 事实回忆失败（1.06%）

**症状**: 简单的事实问题都答不出来

**原因**:
- 实体提取遗漏关键信息
- 图谱中缺少关键节点
- 检索未命中相关记忆

---

## 🎯 紧急修复方案（本周）

### 修复 1: 诊断并修复记忆存储链路

**步骤 1: 运行诊断脚本**
```bash
python diagnose_locomo_failure.py
```

**步骤 2: 检查 Celery Worker**
```bash
# 检查 worker 是否运行
docker ps | grep celery

# 查看 worker 日志
docker logs affinity-celery-worker --tail 100

# 如果未运行，启动 worker
cd backend
celery -A app.worker worker --loglevel=info
```

**步骤 3: 检查 Outbox 积压**
```bash
python backend/check_outbox_status.py
```

如果有大量待处理事件，手动触发处理:
```bash
python backend/app/worker/tasks/outbox.py
```


### 修复 2: 增强检索召回率

**问题**: 当前检索策略可能过于严格，导致召回率极低

**解决方案**: 放宽检索阈值，增加召回数量

**修改文件**: `backend/app/services/retrieval_service.py`

```python
# 当前可能的问题
async def retrieve(self, query: str, top_k: int = 5):
    # 阈值可能太高
    similarity_threshold = 0.8  # 太严格！
    
# 改进方案
async def retrieve(self, query: str, top_k: int = 20):  # 增加召回数量
    # 降低阈值
    similarity_threshold = 0.3  # 更宽松
    
    # 多策略检索
    results = []
    
    # 1. 向量检索（语义相似）
    vector_results = await self.vector_search(query, top_k=10, threshold=0.3)
    results.extend(vector_results)
    
    # 2. 图检索（关系相关）
    graph_results = await self.graph_search(query, top_k=10)
    results.extend(graph_results)
    
    # 3. 关键词检索（精确匹配）
    keyword_results = await self.keyword_search(query, top_k=10)
    results.extend(keyword_results)
    
    # 去重并重排序
    results = self.deduplicate_and_rerank(results, query)
    
    return results[:top_k]
```

**验证**:
```bash
# 测试检索召回率
python test_retrieval_recall.py
```

### 修复 3: 实体提取增强

**问题**: 关键实体未被提取，导致图谱不完整

**解决方案**: 增强实体提取的覆盖率

**修改文件**: `backend/app/services/llm_extraction_service.py`

```python
ENTITY_EXTRACTION_PROMPT = """
从以下对话中提取所有实体和关系。

对话:
{conversation}

要求:
1. 提取所有人物（包括名字、代词）
2. 提取所有地点（国家、城市、街道、建筑）
3. 提取所有时间（日期、时间点、时间段）
4. 提取所有事件（活动、行为、计划）
5. 提取所有属性（职业、爱好、特征、状态）
6. 提取所有关系（家庭、朋友、工作）

输出格式:
{{
    "entities": [
        {{
            "name": "实体名称",
            "type": "PERSON/LOCATION/TIME/EVENT/ATTRIBUTE",
            "properties": {{"key": "value"}},
            "mentions": ["提及1", "提及2"]
        }}
    ],
    "relations": [
        {{
            "source": "实体1",
            "target": "实体2",
            "type": "关系类型",
            "properties": {{"key": "value"}}
        }}
    ]
}}

注意:
- 不要遗漏任何实体
- 同一实体的不同提及要合并
- 保留所有细节信息
"""
```

### 修复 4: 时间实体标准化

**问题**: 时间格式不统一，导致时间推理失败

**解决方案**: 统一时间格式为 ISO 8601

**新增服务**: `backend/app/services/temporal_normalizer.py`

```python
from datetime import datetime
from dateutil import parser
import re

class TemporalNormalizer:
    """时间实体标准化服务"""
    
    def normalize_time(self, time_str: str) -> dict:
        """
        标准化时间字符串
        
        输入: "7 May 2023", "2022", "The sunday before 25 May 2023"
        输出: {"iso": "2023-05-07", "precision": "day", "type": "point"}
        """
        result = {
            "original": time_str,
            "iso": None,
            "precision": None,  # year/month/day/hour/minute/second
            "type": None,  # point/range/relative
        }
        
        # 尝试解析绝对时间
        try:
            dt = parser.parse(time_str, fuzzy=True)
            result["iso"] = dt.isoformat()
            result["type"] = "point"
            
            # 判断精度
            if ":" in time_str:
                if re.search(r'\d{2}:\d{2}:\d{2}', time_str):
                    result["precision"] = "second"
                else:
                    result["precision"] = "minute"
            elif any(month in time_str.lower() for month in [
                "january", "february", "march", "april", "may", "june",
                "july", "august", "september", "october", "november", "december"
            ]):
                result["precision"] = "day"
            elif re.search(r'\d{4}', time_str):
                result["precision"] = "year"
                
        except:
            # 相对时间
            result["type"] = "relative"
            result["reference"] = self.extract_reference_time(time_str)
        
        return result
    
    def extract_reference_time(self, time_str: str) -> str:
        """提取相对时间的参考点"""
        # "The sunday before 25 May 2023" -> "2023-05-25"
        match = re.search(r'\d{1,2}\s+\w+\s+\d{4}', time_str)
        if match:
            return parser.parse(match.group()).isoformat()
        return None
```

---

## 📊 中期优化方案（2-4 周）

### 优化 1: 长对话历史管理

**问题**: LoCoMo 有 1986 个问题，跨越长时间的对话历史

**解决方案**: 实现分层记忆管理

```python
class HierarchicalMemoryManager:
    """分层记忆管理器"""
    
    async def store_memory(self, memory: dict):
        """
        根据重要性和时间分层存储记忆
        
        层级:
        - 工作记忆 (Working Memory): 最近 10 条对话
        - 短期记忆 (Short-term): 最近 100 条对话
        - 长期记忆 (Long-term): 所有历史对话
        """
        # 计算重要性分数
        importance = await self.calculate_importance(memory)
        
        # 存储到不同层级
        await self.working_memory.add(memory)
        
        if importance > 0.5:
            await self.short_term_memory.add(memory)
        
        if importance > 0.7 or self.is_factual(memory):
            await self.long_term_memory.add(memory)
    
    async def retrieve_hierarchical(self, query: str):
        """分层检索"""
        results = []
        
        # 1. 优先从工作记忆检索（最相关）
        results.extend(await self.working_memory.search(query, top_k=5))
        
        # 2. 从短期记忆检索
        if len(results) < 10:
            results.extend(await self.short_term_memory.search(query, top_k=10))
        
        # 3. 从长期记忆检索（事实性信息）
        if len(results) < 15:
            results.extend(await self.long_term_memory.search(query, top_k=10))
        
        return self.deduplicate(results)
```

### 优化 2: 实体链接与消歧

**问题**: 同一实体的不同提及未能关联

**解决方案**: 实体链接服务

```python
class EntityLinker:
    """实体链接服务"""
    
    async def link_entities(self, entities: List[dict]):
        """
        链接同一实体的不同提及
        
        例如:
        - "Caroline" 和 "她" 指向同一人
        - "Sweden" 和 "瑞典" 是同一地点
        """
        linked = []
        
        for entity in entities:
            # 查找已存在的实体
            existing = await self.find_existing_entity(entity)
            
            if existing:
                # 合并到已存在实体
                await self.merge_entity(existing, entity)
                linked.append(existing)
            else:
                # 创建新实体
                new_entity = await self.create_entity(entity)
                linked.append(new_entity)
        
        return linked
    
    async def find_existing_entity(self, entity: dict):
        """查找已存在的实体"""
        # 1. 精确匹配
        exact_match = await self.exact_match(entity["name"])
        if exact_match:
            return exact_match
        
        # 2. 模糊匹配
        fuzzy_matches = await self.fuzzy_match(entity["name"])
        if fuzzy_matches:
            return self.select_best_match(fuzzy_matches, entity)
        
        # 3. 语义匹配
        semantic_matches = await self.semantic_match(entity)
        if semantic_matches:
            return self.select_best_match(semantic_matches, entity)
        
        return None
```


### 优化 3: 多跳推理支持

**问题**: 复杂问题需要多步推理

**解决方案**: 实现多跳检索和推理

```python
class MultiHopReasoner:
    """多跳推理器"""
    
    async def reason(self, question: str, max_hops: int = 3):
        """
        多跳推理
        
        例如:
        问题: "Caroline 4 年前从哪里搬来？"
        
        Hop 1: 检索 "Caroline 搬家" -> 找到 "Caroline 从 Sweden 搬来"
        Hop 2: 检索 "Caroline Sweden 时间" -> 找到 "4 years ago"
        Hop 3: 综合信息 -> 答案: "Sweden"
        """
        context = []
        current_query = question
        
        for hop in range(max_hops):
            # 检索当前查询
            results = await self.retrieve(current_query, top_k=10)
            context.extend(results)
            
            # 判断是否有足够信息
            has_answer, confidence = await self.check_sufficiency(
                question, context
            )
            
            if has_answer and confidence > 0.8:
                break
            
            # 生成下一跳查询
            current_query = await self.generate_next_query(
                question, context
            )
        
        # 生成最终答案
        answer = await self.generate_answer(question, context)
        return answer
```

---

## 🎯 预期改进效果

| 阶段 | 措施 | 预期准确率 | 提升 |
|------|------|-----------|------|
| 当前 | - | 8.36% | - |
| 紧急修复（1周） | 修复存储链路 + 增强检索 | 25%+ | +17% |
| 中期优化（1月） | 分层记忆 + 实体链接 | 40%+ | +15% |
| 长期优化（3月） | 多跳推理 + 时间推理 | 55%+ | +15% |

### 各类别预期提升

| 类别 | 当前 | 1周后 | 1月后 | 3月后 |
|------|------|-------|-------|-------|
| 事实回忆 | 1.06% | 20% | 40% | 60% |
| 时间理解 | 0.62% | 10% | 25% | 45% |
| 推理与推断 | 2.08% | 15% | 35% | 50% |
| 细节理解 | 0.83% | 18% | 38% | 55% |
| **平均** | **8.36%** | **25%** | **40%** | **55%** |

---

## 🚀 立即行动清单

### 今天（必做）

1. **运行诊断脚本**
   ```bash
   python diagnose_locomo_failure.py
   ```

2. **检查 Celery Worker 状态**
   ```bash
   docker ps | grep celery
   docker logs affinity-celery-worker --tail 100
   ```

3. **检查 Outbox 积压**
   ```bash
   python backend/check_outbox_status.py
   ```

4. **如果发现问题，重新同步记忆**
   ```bash
   python backend/resync_memories_to_neo4j.py
   ```

### 本周（高优先级）

1. **降低检索阈值**
   - 修改 `retrieval_service.py`
   - 从 0.8 降到 0.3
   - 增加 top_k 从 5 到 20

2. **增强实体提取**
   - 修改 `llm_extraction_service.py`
   - 使用更详细的提取 prompt
   - 确保不遗漏关键实体

3. **添加时间标准化**
   - 创建 `temporal_normalizer.py`
   - 统一时间格式为 ISO 8601
   - 保留时间精度信息

4. **验证改进效果**
   ```bash
   # 重新运行 LoCoMo 评测（小规模）
   python evals/run_full_locomo_pipeline.py --limit 100
   ```

### 下周（中优先级）

1. **实现分层记忆管理**
2. **添加实体链接服务**
3. **优化检索策略**
4. **运行完整 LoCoMo 评测**

---

## 📊 监控指标

### 关键指标

1. **检索召回率**
   - 目标: 从 < 10% 提升到 60%+
   - 测量: 检索到相关记忆的比例

2. **实体覆盖率**
   - 目标: 从 ? 提升到 80%+
   - 测量: 提取的实体 / 应提取的实体

3. **Outbox 处理延迟**
   - 目标: P50 < 2s, P95 < 30s
   - 测量: 事件创建到处理完成的时间

4. **各类别准确率**
   - 事实回忆: 1.06% → 20%+
   - 时间理解: 0.62% → 10%+
   - 推理与推断: 2.08% → 15%+
   - 细节理解: 0.83% → 18%+

---

## 💡 关键洞察

### 为什么 LoCoMo 比 KnowMeBench 差这么多？

1. **数据量差异**
   - KnowMeBench: 21 题（快速测试）
   - LoCoMo: 1986 题（长对话历史）

2. **任务复杂度**
   - KnowMeBench: 短上下文，明确问题
   - LoCoMo: 长对话历史，需要跨多轮对话检索

3. **系统瓶颈**
   - KnowMeBench 暴露了 prompt 和推理问题
   - LoCoMo 暴露了存储和检索的根本问题

### 核心问题

**LoCoMo 的 8.36% 准确率说明你的系统在长期记忆存储和检索上存在根本性问题！**

这不是 prompt 优化能解决的，需要：
1. 修复记忆存储链路
2. 大幅提升检索召回率
3. 实现真正的长期记忆管理

---

## 📝 Git 提交建议

```bash
# 紧急修复
git commit -m "Fix: 修复记忆存储链路，确保 Outbox 正常处理"
git commit -m "Fix: 降低检索阈值，提升召回率"
git commit -m "Add: 增强实体提取覆盖率"
git commit -m "Add: 时间实体标准化服务"

# 中期优化
git commit -m "Add: 分层记忆管理系统"
git commit -m "Add: 实体链接与消歧服务"
git commit -m "Add: 多跳推理支持"

# 验证
git commit -m "Test: LoCoMo 评测准确率提升到 25%+"
```

---

**总结**: LoCoMo 的极低准确率（8.36%）暴露了系统在长期记忆管理上的根本问题。优先修复存储链路和检索召回率，预期 1 周内可提升到 25%+，1 个月内达到 40%+。
