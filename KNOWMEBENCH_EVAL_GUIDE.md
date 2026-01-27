# KnowMeBench 评测指南

## 概述

KnowMeBench 是一个专门评测 AI 系统长期记忆能力的基准测试。你的项目已经完整集成了 KnowMeBench 评测框架，可以调用真实的 LLM 返回真实的评测结果。

## 评测能力

KnowMeBench Dataset1 包含 7 种任务类型：

1. **Information Extraction** - 信息抽取：精准提取实体和事实
2. **Adversarial Abstention** - 对抗性克制：识别陷阱问题并拒答
3. **Temporal Reasoning** - 时间推理：时间顺序和持续时长推理
4. **Logical Event Ordering** - 逻辑事件排序：按危险程度等维度排序
5. **Mnestic Trigger Analysis** - 记忆触发分析：识别触发回忆的线索
6. **Mind-Body Interaction** - 心身交互：解释心理-生理矛盾
7. **Expert-Annotated Psychoanalysis** - 专家标注心理分析：深层心理动机洞察

## 前置条件

### 1. 后端服务必须运行

```bash
cd backend

# 启动所有依赖服务（PostgreSQL, Neo4j, Redis, Milvus）
docker-compose up -d

# 启动后端 API（端口 8000）
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

验证服务：
```bash
curl http://localhost:8000/api/v1/health
```

### 2. 配置已就绪

你的配置文件 `evals/.env.local` 已经配置好：
- ✅ OpenAI 兼容 API Key（硅基流动）
- ✅ Judge 模型：DeepSeek-V3
- ✅ 后端地址：http://localhost:8000

## 快速开始

### 步骤 1：运行评测（生成模型输出）

```bash
# 在项目根目录执行
python evals/run_knowmebench_dataset1_pipeline.py \
  --backend_base_url http://localhost:8000 \
  --mode graph_only \
  --eval_mode \
  --concurrency 6
```

**参数说明：**
- `--backend_base_url`: 后端 API 地址（默认 http://localhost:8000）
- `--mode`: 检索模式
  - `graph_only`: 仅使用图检索（推荐用于评测记忆图谱能力）
  - `hybrid`: 向量+图混合检索
- `--eval_mode`: 启用评测模式（跳过某些生产环境的处理）
- `--concurrency`: 并发数（默认 4，可调整为 6-8）
- `--limit_per_task`: 限制每个任务的题目数量（可选，用于快速测试）
- `--task`: 指定运行特定任务（可多次使用，不指定则运行全部）

**快速测试示例（每个任务只跑 5 题）：**
```bash
python evals/run_knowmebench_dataset1_pipeline.py \
  --backend_base_url http://localhost:8000 \
  --mode graph_only \
  --eval_mode \
  --limit_per_task 5 \
  --concurrency 4
```

**运行特定任务：**
```bash
python evals/run_knowmebench_dataset1_pipeline.py \
  --backend_base_url http://localhost:8000 \
  --mode graph_only \
  --eval_mode \
  --task "Information Extraction" \
  --task "Adversarial Abstention"
```

**输出位置：**
```
outputs/knowmebench_run/ds1_pipeline_graph_only_<timestamp>/
├── knowmebench.dataset1.<task>.model_outputs.json  # 每个任务的输出
├── merged_for_official_eval.json                   # 合并后的所有输出
└── knowmebench.dataset1.<timestamp>.run_summary.json  # 运行摘要
```

### 步骤 2：运行 Judge 评分

```bash
# 对步骤 1 的输出进行评分
python evals/run_knowmebench_official_judge.py \
  --input_dir outputs/knowmebench_run/ds1_pipeline_graph_only_<timestamp> \
  --output_file outputs/knowmebench_run/ds1_pipeline_graph_only_<timestamp>/judge_results.json \
  --judge_model Pro/deepseek-ai/DeepSeek-V3.2 \
  --concurrency 4
```

**参数说明：**
- `--input_dir`: 步骤 1 生成的输出目录
- `--output_file`: Judge 结果输出文件
- `--judge_model`: Judge 使用的模型（默认从 .env.local 读取）
- `--concurrency`: 并发数

**输出格式：**
```json
{
  "meta": {
    "judge_model": "Pro/deepseek-ai/DeepSeek-V3.2",
    "total_items": 100,
    "evaluated_items": 98,
    "average_score": 3.45
  },
  "details": [
    {
      "id": 1,
      "task_type": "Information Extraction",
      "score": 5,
      "reasoning": "关键事实完全正确且无多余编造",
      "status": "success"
    }
  ]
}
```

**评分标准（0-5 分）：**
- **5 分**：完全正确，无编造
- **3 分**：部分正确或轻微偏差
- **1 分**：大部分错误或明显编造
- **0 分**：严重编造或与参考答案相反

## 完整评测流程示例

```bash
# 1. 启动后端服务
cd backend
docker-compose up -d
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# 2. 在新终端运行评测（完整版）
cd ..
python evals/run_knowmebench_dataset1_pipeline.py \
  --backend_base_url http://localhost:8000 \
  --mode graph_only \
  --eval_mode \
  --concurrency 6

# 3. 记录输出目录（例如：outputs/knowmebench_run/ds1_pipeline_graph_only_20260126_143022）
# 脚本会在最后一行打印输出目录路径

# 4. 运行 Judge 评分
python evals/run_knowmebench_official_judge.py \
  --input_dir outputs/knowmebench_run/ds1_pipeline_graph_only_20260126_143022 \
  --output_file outputs/knowmebench_run/ds1_pipeline_graph_only_20260126_143022/judge_results.json \
  --judge_model Pro/deepseek-ai/DeepSeek-V3.2 \
  --concurrency 4

# 5. 查看结果
cat outputs/knowmebench_run/ds1_pipeline_graph_only_20260126_143022/judge_results.json
```

## 评测模式对比

### graph_only vs hybrid

| 模式 | 检索策略 | 适用场景 |
|------|---------|---------|
| `graph_only` | 仅使用 Neo4j 图检索 | 评测记忆图谱的关系推理能力 |
| `hybrid` | 向量（Milvus）+ 图混合检索 | 评测综合检索能力 |

**建议：**
- 首次评测使用 `graph_only`，专注评测记忆图谱能力
- 后续可对比 `hybrid` 模式，评估混合检索的提升效果

## 性能优化建议

### 1. 并发调优
- 本地测试：`--concurrency 4`
- 生产环境：`--concurrency 6-8`
- 注意：并发过高可能触发 API 限流

### 2. 快速验证
```bash
# 每个任务只跑 3 题，快速验证流程
python affinity_evals/knowmebench/run_dataset1_pipeline.py \
  --backend_base_url http://localhost:8010 \
  --mode graph_only \
  --eval_mode \
  --limit_per_task 3 \
  --concurrency 2
```

### 3. 分批运行
```bash
# 先跑简单任务
python affinity_evals/knowmebench/run_dataset1_pipeline.py \
  --backend_base_url http://localhost:8010 \
  --mode graph_only \
  --eval_mode \
  --task "Information Extraction" \
  --task "Adversarial Abstention"

# 再跑复杂任务
python affinity_evals/knowmebench/run_dataset1_pipeline.py \
  --backend_base_url http://localhost:8010 \
  --mode graph_only \
  --eval_mode \
  --task "Expert-Annotated Psychoanalysis" \
  --task "Mind-Body Interaction"
```

## 常见问题

### Q1: 后端连接失败
**错误：** `failed_to_get_token` 或 `backend_request_failed`

**解决：**
```bash
# 检查后端是否运行
curl http://localhost:8000/api/v1/health

# 确保 --backend_base_url 参数正确
```

### Q2: Judge 评分失败
**错误：** `RateLimitError` 或 `429`

**解决：**
- 降低并发：`--concurrency 2`
- 检查 API Key 额度
- 等待一段时间后重试

### Q3: 内存不足
**解决：**
- 降低并发数
- 使用 `--limit_per_task` 分批运行
- 确保 Docker 容器有足够内存

### Q4: 评测结果不理想
**分析方向：**
1. 检查 `model_outputs.json` 中的 `model_answer` 是否合理
2. 查看 `meta.context_source` 确认检索是否命中相关记忆
3. 对比 `reference_answer` 和 `model_answer` 的差异
4. 检查 `meta.error` 字段是否有错误信息

## 历史评测结果

你的项目已经运行过多次评测，结果位于：
```
evals/reports/
├── report_20260125_*.md      # 评测报告
├── meta_20260125_*.json      # 元数据
└── run_20260125_*.log        # 运行日志
```

查看最新报告：
```bash
ls -lt evals/reports/report_*.md | head -1
```

## 下一步

1. **启动后端服务**（如果还没启动）
2. **运行快速测试**（3-5 题/任务）验证流程
3. **运行完整评测**（所有任务）
4. **分析结果**并优化系统
5. **对比不同模式**（graph_only vs hybrid）

## 技术细节

### 评测流程
1. 从 KnowMeBench 数据集加载问题和参考答案
2. 根据问题中的日期或 evidence_ids 构建上下文
3. 调用后端 API `/api/v1/conversation/message` 获取模型回答
4. 保存模型输出到 JSON 文件
5. 使用 LLM Judge 对模型回答进行评分（0-5 分）
6. 生成评测报告

### 上下文构建策略
- **基于日期**：从问题中提取日期，检索该日期的所有记录
- **基于 evidence_ids**：使用参考答案中的 evidence_ids，检索相关记录及其上下文窗口（默认 ±30 条）

### Judge 评分原则
- 以 `reference_answer` 为准
- 对编造内容重罚
- 对"不知道"的正确拒答给高分
- 不奖励文采，只评测准确性

## 相关文档

- KnowMeBench 官方仓库：`external/KnowMeBench/`
- 评测框架代码：`affinity_evals/knowmebench/`
- 历史评测结果：`evals/reports/`
- 后端 API 文档：http://localhost:8000/docs

---

**祝评测顺利！如有问题，请查看日志文件或联系开发团队。**
