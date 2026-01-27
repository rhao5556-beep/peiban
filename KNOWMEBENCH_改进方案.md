# KnowMeBench 评测改进方案

基于评测结果（平均分 3.29/5.0），针对弱项任务提出系统性改进方案。

## ⚠️ 重要说明（与当前仓库实现对齐）

1. **可改的评测入口脚本**在 [run_knowmebench_dataset1_pipeline.py](file:///c:/Users/murphy/Desktop/%E9%99%AA%E4%BC%B4%E9%A1%B9%E7%9B%AE/evals/run_knowmebench_dataset1_pipeline.py)，而不是 `affinity_evals/knowmebench/*.py`（仓库内该路径缺少可读源码）。
2. 当前后端 `POST /api/v1/conversation/message` 的请求体 **不包含 `eval_mode`/`task_type` 字段**（见 [conversation.py](file:///c:/Users/murphy/Desktop/%E9%99%AA%E4%BC%B4%E9%A1%B9%E7%9B%AE/backend/app/api/endpoints/conversation.py#L24-L30)），因此评测脚本发出的 `eval_mode` 目前不会触发任何“评测专用隔离/路由”逻辑。
3. `graph_only` 目前只“物理隔离了 history”，但仍会并行执行向量检索（见 [conversation_service.py](file:///c:/Users/murphy/Desktop/%E9%99%AA%E4%BC%B4%E9%A1%B9%E7%9B%AE/backend/app/services/conversation_service.py#L528-L546)）。如果后续在“有向量记忆的用户”上评测，会污染 graph_only 的评测假设，因此建议把“真正 graph_only”列为 P0 修复。
4. Dataset1 评测脚本会把 **record excerpt 直接拼进用户 message**，所以“信息提取满分”更多是“给定上下文的阅读理解”，并非图谱/向量检索能力；针对 KnowMeBench 的改动应优先约束“只能用注入上下文作证据、不得编造/不得引入额外事件”。

## 📊 问题诊断

### 🔴 高优先级问题（P0）

#### 1. 时间推理能力弱（1.67/5.0）
**问题表现**：
- 时间计算错误（相差 1 分钟）
- 时间逻辑推理错误
- 缺少精确的时间细节（如 10 秒）

**根本原因**：
- 时间实体提取不够精确
- 缺少专门的时间计算模块
- LLM 对时间推理的 prompt 不够明确

#### 2. 深层心理分析不足（1.33/5.0）
**问题表现**：
- 未提供任何洞察（0 分）
- 分析过于泛泛，未触及核心动机
- 引入了参考答案中没有的元素

**根本原因**：
- 缺少心理分析的专门 prompt
- 检索到的上下文可能不够深入
- LLM 倾向于给出通用回答而非深层洞察

#### 3. 偶尔编造信息（Adversarial Abstention: 3.33/5.0）
**问题表现**：
- 在信息不足时编造具体细节
- 未能明确表示"不知道"

**根本原因**：
- 缺少“证据引用/证据覆盖”机制（回答没有被强制绑定到上下文证据）
- 当前后端没有“评测模式的拒答策略”，只能依赖通用 Prompt 约束，遇到诱导提问时仍可能“补全细节”


### 🟡 中优先级问题（P1）

#### 4. 逻辑事件排序不稳定（3.0/5.0）
**问题表现**：
- 未按参考顺序排列
- 引入了新事件
- 部分正确但有偏差

**根本原因**：
- 排序逻辑依赖 LLM 推理，不够稳定
- 可能引入检索外的信息

#### 5. 地理位置识别不准确
**问题表现**：
- 错误识别地点（Bærum vs Thereses Street）

**根本原因**：
- 地理实体识别不够精确
- 可能是实体提取或检索问题

---

## 🎯 改进方案

### Phase 1: 快速修复（1-2 周）

#### 方案 1.1: 增强"不知道"判断机制
**目标**: 提升 Adversarial Abstention 从 3.33 → 4.5+

**实施步骤**：
1. 为对话接口增加 `eval_mode` 与 `eval_task_type`（可选）字段，让后端能做“评测专用策略”
2. 在评测模式下启用“证据引用约束”：每个具体事实必须能在注入上下文中找到原文支撑，否则拒答
3. 对 Adversarial Abstention 启用更严格的拒答模板（信息不足时直接拒答，而不是尝试补全）

**代码位置（建议）**:
- `backend/app/api/endpoints/conversation.py`（请求体字段）
- `backend/app/services/conversation_service.py`（Prompt/策略）

**Prompt 优化示例**：
```python
SYSTEM_PROMPT = """
你是一个严谨的 AI 助手。回答问题时：
1. 仅基于已提供的证据上下文回答（评测模式下：以“记录上下文”为证据）
2. 每个具体事实必须能在证据中找到原文支撑；找不到就拒答
3. 绝对不要编造细节；不确定时直接说明信息不足
"""
```


#### 方案 1.2: 优化时间实体提取
**目标**: 提升 Temporal Reasoning 从 1.67 → 3.0+

**实施步骤**：
1. 在评测模式下对 Temporal Reasoning 启用“精确计算”策略（优先用代码计算，其次再让 LLM 解释）
2. 统一对输出做“精度约束”：题目要求到秒就必须输出到秒，禁止四舍五入
3. 对输入里的时间表达做结构化抽取（时间点/持续时长/区间），再做计算与输出格式化

**代码位置（建议）**:
- `backend/app/services/conversation_service.py`（回答侧策略更直接影响 KnowMeBench 分数）
- （可选）新增 `backend/app/services/temporal_reasoning_service.py` 提供可复用计算能力

> 说明：`llm_extraction_service.py` 主要影响“图谱写入/长期记忆抽取”，对 Dataset1 这种“直接注入上下文”的评测收益有限；时间推理分数更依赖回答阶段的精确计算与格式约束。

**改进点**：
```python
# 目标：保留完整时间信息并可计算（精确到秒）
{
    "entity_type": "TIME",
    "value": "2024-01-15 14:30:45",  # 精确到秒
    "duration": "1 hour 15 minutes 10 seconds",  # 保留完整时长
    "precision": "second"  # 标注精度
}
```

#### 方案 1.3: 严格信息边界控制
**目标**: 提升 Logical Event Ordering 从 3.0 → 4.0+

**实施步骤**：
1. 在生成回答前，验证所有信息都来自检索结果
2. 添加"信息来源标注"机制
3. Prompt 中明确禁止引入外部信息

**Prompt 优化**：
```python
ORDERING_PROMPT = """
请根据以下上下文对事件排序：
{context}

要求：
1. 仅使用上述上下文中的事件
2. 不要添加任何上下文中没有的事件
3. 严格按照指定维度排序
4. 如果信息不足以排序，明确说明
"""
```


---

### Phase 2: 中期优化（2-4 周）

#### 方案 2.1: 引入时间推理模块
**目标**: 提升 Temporal Reasoning 从 3.0 → 4.0+

**实施步骤**：
1. 创建 `temporal_reasoning_service.py`
2. 实现时间计算、时长推理、时间关系判断
3. 集成到 conversation_service

**新增服务**：
```python
# backend/app/services/temporal_reasoning_service.py
class TemporalReasoningService:
    async def calculate_duration(self, start_time, end_time):
        """精确计算时间间隔"""
        pass
    
    async def infer_temporal_order(self, events):
        """推理事件时间顺序"""
        pass
    
    async def extract_temporal_relations(self, text):
        """提取时间关系（before, after, during）"""
        pass
```

**集成点**: 在 `conversation_service.py` 中，检测到时间推理任务时调用此服务

#### 方案 2.2: 心理分析 Prompt 工程
**目标**: 提升 Expert Psychoanalysis 从 1.33 → 3.0+

**实施步骤**：
1. 设计专门的心理分析 prompt 模板
2. 采用结构化输出（观察→机制→动机→证据引用），避免泛泛而谈
3. 明确禁止引入证据外的新人物/新事件/新因果链（这是扣分点之一）

**Prompt 模板**：
```python
PSYCHOANALYSIS_PROMPT = """
你是一位经验丰富的心理分析师。请分析以下情境：

上下文：
{context}

问题：
{question}

分析步骤：
1. 观察到的表层行为/现象
2. 可能的心理机制
3. 深层动机和潜意识因素
4. 与过往经历的关联

要求：
- 每条洞察后附上你引用的证据片段（从上下文逐字摘取一小段）
- 不要引入上下文中没有的具体情节/人物/地点
"""
```



#### 方案 2.3: 任务类型自动识别与路由
**目标**: 针对不同任务类型使用不同策略

**实施步骤**：
1. 评测模式优先由评测脚本显式传入 `eval_task_type`，避免靠关键词猜任务
2. 根据 task_type 选择不同的 prompt 与约束（如：Temporal 要计算、Ordering 要禁止新增事件、Abstention 要更严格拒答）
3. 非评测模式再退化为轻量分类器（可选）

**实现示例**：
```python
class TaskRouter:
    async def classify_task(self, question: str) -> str:
        """识别任务类型"""
        # 时间推理：包含时间词汇
        # 心理分析：包含"为什么"、"动机"等
        # 信息抽取：包含"什么"、"谁"等
        pass
    
    async def get_prompt_template(self, task_type: str) -> str:
        """根据任务类型返回优化的 prompt"""
        templates = {
            "temporal_reasoning": TEMPORAL_PROMPT,
            "psychoanalysis": PSYCHOANALYSIS_PROMPT,
            "information_extraction": EXTRACTION_PROMPT,
            "adversarial": ADVERSARIAL_PROMPT,
        }
        return templates.get(task_type, DEFAULT_PROMPT)
```

#### 方案 2.4: 增强地理实体识别
**目标**: 提升地理位置准确性

**实施步骤**：
1. 对“地点类答案”启用“原文优先”策略：优先输出上下文中出现的地点字符串（逐字匹配），禁止用常识替换为“更知名/更大范围”的地点
2. 若上下文出现多个地点且问题未指明，列出候选并说明各自证据（避免猜）
3. 只有当业务侧确实需要（非评测）才引入地理数据库/坐标等外部依赖

**改进点**：
```python
{
    "entity_type": "LOCATION",
    "value": "Thereses Street",
    "hierarchy": {
        "street": "Thereses Street",
        "district": "Berlunn",
        "city": "Oslo",
        "country": "Norway"
    },
    "coordinates": {"lat": 59.9139, "lon": 10.7522}  # 可选
}
```


---

### Phase 3: 长期优化（1-2 月）

#### 方案 3.1: 混合检索模式对比
**目标**: 评估 hybrid 模式是否优于 graph_only

**实施步骤**：
1. 运行完整 KnowMeBench 评测（hybrid 模式）
2. 对比 graph_only vs hybrid 的表现
3. 分析哪些任务类型受益于向量检索

**评测命令**：
```bash
# Graph only
python evals/run_knowmebench_dataset1_pipeline.py --mode graph_only --eval_mode --concurrency 6

# Hybrid
python evals/run_knowmebench_dataset1_pipeline.py --mode hybrid --eval_mode --concurrency 6
```

#### 方案 3.2: 多跳推理增强
**目标**: 提升复杂推理任务能力

**实施步骤**：
1. 实现多跳图检索（当前可能只检索 1-hop）
2. 添加推理链追踪
3. 支持"检索-推理-再检索"的迭代模式

**架构改进**：
```python
class MultiHopReasoningService:
    async def reason_with_retrieval(self, question, max_hops=3):
        """迭代检索和推理"""
        context = []
        for hop in range(max_hops):
            # 1. 基于当前上下文生成子问题
            sub_questions = await self.generate_sub_questions(question, context)
            
            # 2. 检索子问题的答案
            new_context = await self.retrieve(sub_questions)
            context.extend(new_context)
            
            # 3. 判断是否有足够信息回答
            if await self.is_sufficient(question, context):
                break
        
        return await self.generate_answer(question, context)
```


#### 方案 3.3: 领域知识注入
**目标**: 引入心理学、时间推理等领域知识

**实施步骤**：
1. 构建心理学知识库（常见心理机制、防御机制等）
2. 构建时间推理规则库
3. 在回答生成时参考领域知识

**知识库示例**：
```python
PSYCHOLOGY_KNOWLEDGE = {
    "defense_mechanisms": [
        "denial", "projection", "rationalization", "displacement"
    ],
    "cognitive_biases": [
        "confirmation_bias", "anchoring", "availability_heuristic"
    ],
    "emotional_patterns": {
        "avoidance": "回避挑战性情境以减少焦虑",
        "compensation": "通过其他方式弥补不足感"
    }
}

TEMPORAL_RULES = {
    "duration_calculation": "end_time - start_time",
    "sequence_inference": "基于时间戳或时间连接词推断顺序",
    "time_precision": "保留原始精度，不要四舍五入"
}
```

#### 方案 3.4: 评测驱动的持续优化
**目标**: 建立评测-优化-再评测的闭环

**实施步骤**：
1. 定期运行 KnowMeBench 完整评测（每周/每月）
2. 分析新的失败案例
3. 针对性优化
4. 追踪各任务类型的分数趋势

**自动化脚本**：
```bash
# 每周自动评测
# weekly_eval.bat
python evals/run_knowmebench_dataset1_pipeline.py --mode graph_only --eval_mode
python generate_trend_report.py  # 生成趋势报告
```


---

## 📋 实施优先级与时间表

### 立即实施（本周）- Quick Wins

| 方案 | 预期提升 | 工作量 | 风险 |
|------|---------|--------|------|
| 1.1 增强"不知道"判断 | 3.33→4.5 | 2 天 | 低 |
| 1.3 严格信息边界控制 | 3.0→4.0 | 1 天 | 低 |

**总预期提升**: 平均分 3.29 → 3.8+

### 短期实施（2-4 周）

| 方案 | 预期提升 | 工作量 | 风险 |
|------|---------|--------|------|
| 1.2 优化时间实体提取 | 1.67→3.0 | 3 天 | 中 |
| 2.2 心理分析 Prompt 工程 | 1.33→3.0 | 3 天 | 低 |
| 2.3 任务类型路由 | 整体+0.3 | 5 天 | 中 |
| 2.4 地理实体识别 | 局部提升 | 2 天 | 低 |

**总预期提升**: 平均分 3.8 → 4.2+

### 中期实施（1-2 月）

| 方案 | 预期提升 | 工作量 | 风险 |
|------|---------|--------|------|
| 2.1 时间推理模块 | 3.0→4.0 | 2 周 | 中 |
| 3.1 混合检索对比 | 待评估 | 1 周 | 低 |
| 3.2 多跳推理 | 整体+0.2 | 3 周 | 高 |
| 3.3 领域知识注入 | 整体+0.3 | 2 周 | 中 |

**总预期提升**: 平均分 4.2 → 4.5+

---

## 🎯 目标设定

### 短期目标（1 个月）
- **平均分**: 3.29 → 4.0+
- **满分题目比例**: 57% → 70%+
- **0-1 分题目**: 28.6% → 10%

### 中期目标（3 个月）
- **平均分**: 4.0 → 4.3+
- **所有任务类型**: ≥ 3.0 分
- **核心任务**: Information Extraction, Mind-Body ≥ 4.5 分

### 长期目标（6 个月）
- **平均分**: 4.3 → 4.5+
- **接近人类水平**: 在部分任务上达到专家级表现

---

## 🔧 具体实施指南

### 第一步：增强"不知道"判断（本周）

**修改文件（建议最小闭环）**:
- `backend/app/api/endpoints/conversation.py`（增加 `eval_mode` / `eval_task_type`）
- `backend/app/services/conversation_service.py`（评测模式 Prompt 与拒答策略）

**修改内容**:
```python
# 推荐策略（避免再加一次 LLM 调用做 sufficiency，既耗时又容易“自证充分”）：
# 1) 评测模式下，强制“证据引用”：每个具体事实都要引用注入上下文中的原文片段
# 2) 若无法引用到关键事实（或上下文明显不含该信息），直接拒答
# 3) 对 Adversarial Abstention 任务，优先使用更严格拒答模板
#
# 技术落点：
# - 请求体加入 eval_mode / eval_task_type
# - _build_prompt 在 eval_mode 下追加“证据引用/禁止补全细节”的规则
# - 生成回答后做一次简单的后验检查：若回答出现大量上下文未出现的专有名词/地点/数字，则改为拒答或降级为“信息不足”
```

**验证方法**:
```bash
# 运行 Adversarial Abstention 测试
python evals/run_knowmebench_dataset1_pipeline.py --mode graph_only --eval_mode --task "Adversarial Abstention" --limit_per_task 10
```

**预期结果**: Adversarial Abstention 分数从 3.33 提升到 4.0+


### 第二步：优化时间实体提取（下周）

**修改文件（优先回答侧）**:
- `backend/app/services/conversation_service.py`
- （可选）新增 `backend/app/services/temporal_reasoning_service.py`

**修改内容**:
```python
# 推荐策略：
# - 先从上下文中抽取时间点/区间/时长（允许 LLM，但要结构化输出）
# - 时间计算尽量走代码（datetime/正则即可覆盖 KnowMeBench 常见格式）
# - 输出严格保留题目要求的精度（秒级、分钟级），禁止四舍五入
```

**验证方法**:
```bash
# 运行 Temporal Reasoning 测试
python evals/run_knowmebench_dataset1_pipeline.py --mode graph_only --eval_mode --task "Temporal Reasoning" --limit_per_task 10
```

**预期结果**: Temporal Reasoning 分数从 1.67 提升到 2.5+

---

## 📊 监控与评估

### 关键指标

1. **任务级指标**
   - 各任务类型平均分
   - 满分题目比例
   - 0-1 分题目比例

2. **系统级指标**
   - 整体平均分
   - 分数分布
   - 改进趋势

3. **质量指标**
   - 编造率（Hallucination Rate）
   - 拒答准确率（Abstention Accuracy）
   - 信息提取准确率

### 评估流程

```bash
# 1. 每周运行快速评测
run_knowmebench_eval.bat quick

# 2. 每月运行完整评测
run_knowmebench_eval.bat full

# 3. 生成趋势报告
python generate_trend_report.py

# 4. 对比不同版本
python compare_eval_results.py \
  --baseline outputs/knowmebench_run/baseline \
  --current outputs/knowmebench_run/current
```

---

## 💡 最佳实践

### Prompt 设计原则

1. **明确性**: 清晰说明任务要求
2. **约束性**: 明确禁止的行为（如编造）
3. **示例性**: 提供 few-shot 示例
4. **结构化**: 使用结构化输出格式

### 测试驱动开发

1. **先写测试**: 针对弱项任务编写测试用例
2. **小步迭代**: 每次只改进一个方面
3. **持续验证**: 每次修改后运行评测
4. **回归测试**: 确保不影响已有功能

### 代码质量

1. **遵守异步规范**: 所有 I/O 操作使用 async/await
2. **保持 Outbox 模式**: 不直接写入 Neo4j/Milvus
3. **添加日志**: 记录关键决策点
4. **错误处理**: 优雅处理异常情况

---

## 🚀 快速开始

### 立即行动清单

**今天**:
- [ ] 阅读完整改进方案
- [ ] 确定优先实施的方案（建议：1.1 + 1.3）
- [ ] 创建开发分支

**本周**:
- [ ] 实施方案 1.1（增强"不知道"判断）
- [ ] 实施方案 1.3（严格信息边界）
- [ ] 运行快速评测验证效果
- [ ] 提交代码并记录改进

**下周**:
- [ ] 实施方案 1.2（时间实体提取）
- [ ] 实施方案 2.2（心理分析 Prompt）
- [ ] 运行完整评测
- [ ] 对比两次评测的 EVALUATION_REPORT/judge_results

---

## 📚 参考资源

### 相关文档
- `KNOWMEBENCH_EVAL_GUIDE.md` - 评测指南
- `backend/docs/ARCHITECTURE.md` - 系统架构
- `backend/app/services/conversation_service.py` - 对话服务

### 评测数据
- `outputs/knowmebench_run/` - 历史评测结果
- `external/KnowMeBench/` - 官方数据集

### 工具脚本
- `run_knowmebench_eval.bat` - 快捷评测脚本
- `evals/run_knowmebench_dataset1_pipeline.py` - Dataset1 评测入口（可读源码）

---

## 📝 Git 提交建议

```bash
# 阶段 1: 快速修复
git commit -m "Fix: 增强信息不足时的拒答判断机制"
git commit -m "Fix: 严格控制信息边界，避免引入检索外信息"

# 阶段 2: 功能增强
git commit -m "Add: 优化时间实体提取，保留完整精度"
git commit -m "Add: 心理分析专用 Prompt 模板"
git commit -m "Add: 任务类型自动识别与路由"

# 阶段 3: 架构优化
git commit -m "Add: 时间推理专用服务模块"
git commit -m "Add: 多跳推理支持"
git commit -m "Add: 领域知识库集成"
```

---

**总结**: 通过系统性的改进，预期在 1 个月内将平均分从 3.29 提升到 4.0+，在 3 个月内达到 4.3+。重点关注时间推理和心理分析两个弱项，同时保持信息抽取等优势任务的表现。
