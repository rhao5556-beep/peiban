# LoCoMo 评测指南

## 简介

LoCoMo (Long-term Conversation Memory) 是一个评测长期记忆系统的基准测试。本项目已集成完整的 LoCoMo 评测流程，支持使用真实 LLM 进行智能评分。

## 快速开始

### 1. 准备工作

确保后端服务正在运行：

```bash
cd backend
start-dev.bat
```

### 2. 运行完整评测

```bash
# 运行完整评测（所有对话和问题）
evals\run_full_locomo_pipeline.bat

# 或者限制评测规模（快速测试）
evals\run_full_locomo_pipeline.bat --limit_conversations 2 --limit_questions 10
```

### 3. 查看结果

评测完成后，结果保存在 `outputs/locomo_run/locomo10_hybrid_YYYYMMDD_HHMMSS/` 目录：

- `EVALUATION_REPORT.md` - 人类可读的评测报告
- `scoring_summary.json` - 总体指标
- `failures.json` - 失败案例分析
- `detailed_scores.json` - 所有问题的详细评分

## 评测流程说明

### 第 1 步：运行评测

脚本会：
1. 将 LoCoMo 对话历史注入到系统中
2. 向系统提问（测试长期记忆能力）
3. 收集系统的回答

### 第 2 步：LLM 评分

使用真实 LLM（DeepSeek-V3）作为评判者：
- 对比系统回答和参考答案
- 支持语义理解（不仅仅是字符串匹配）
- 为每个答案提供置信度和推理过程

### 第 3 步：生成报告

自动生成包含以下内容的报告：
- 总体准确率
- 按问题类型分类的性能
- 失败案例分析
- 改进建议

## 问题类型

LoCoMo 包含 4 种问题类型：

1. **Factual Recall (事实回忆)** - 直接从对话中提取事实
   - 例：Caroline 的宠物是什么？

2. **Temporal Understanding (时间理解)** - 时间相关信息
   - 例：Caroline 什么时候去的 LGBTQ 支持小组？

3. **Reasoning & Inference (推理)** - 需要推理的问题
   - 例：Caroline 会追求写作作为职业选择吗？

4. **Detailed Understanding (细节理解)** - 详细的上下文理解
   - 例：Melanie 为什么选择在陶艺项目中使用颜色和图案？

## 高级用法

### 仅运行评测（不评分）

```bash
python evals/run_locomo10_pipeline.py ^
    --backend_base_url http://localhost:8000 ^
    --dataset_path data/locomo/locomo10.json ^
    --output_dir outputs/locomo_run ^
    --mode hybrid ^
    --limit_conversations 2
```

### 仅评分（使用已有结果）

```bash
python evals/score_locomo_with_llm.py ^
    --in_path outputs/locomo_run/locomo10_hybrid_YYYYMMDD_HHMMSS/locomo.locomo10.YYYYMMDD_HHMMSS.model_outputs.json ^
    --out_path outputs/locomo_run/locomo10_hybrid_YYYYMMDD_HHMMSS/scoring_summary.json ^
    --failures_out_path outputs/locomo_run/locomo10_hybrid_YYYYMMDD_HHMMSS/failures.json ^
    --detailed_out_path outputs/locomo_run/locomo10_hybrid_YYYYMMDD_HHMMSS/detailed_scores.json ^
    --use_llm
```

### 使用精确匹配评分（不使用 LLM）

```bash
python evals/score_locomo_with_llm.py ^
    --in_path <model_outputs.json> ^
    --out_path <summary.json> ^
    --no_llm
```

### 自定义 LLM 评判模型

```bash
set OPENAI_API_KEY=your_api_key
set OPENAI_API_BASE=https://api.openai.com/v1
set OPENAI_MODEL=gpt-4

evals\run_full_locomo_pipeline.bat
```

## 评测模式

系统支持两种检索模式：

- `hybrid` (默认) - 混合检索（向量 + 图）
- `graph_only` - 仅图检索

```bash
evals\run_full_locomo_pipeline.bat --mode graph_only
```

## 性能优化

### 快速测试

```bash
# 只测试 1 个对话，每个对话 5 个问题
evals\run_full_locomo_pipeline.bat --limit_conversations 1 --limit_questions 5
```

### 调整 API 调用频率

修改 `run_full_locomo_pipeline.bat` 中的 `--rate_limit_delay` 参数：

```bash
--rate_limit_delay 0.5  # 每次 API 调用间隔 0.5 秒
```

## 结果解读

### 准确率指标

- **Accuracy** - LLM 评判的准确率（语义理解）
- **Exact Match Accuracy** - 精确匹配准确率（字符串匹配）
- **Average Confidence** - LLM 评判的平均置信度

### 性能基准

- **优秀**: Accuracy ≥ 80%
- **良好**: Accuracy ≥ 60%
- **需改进**: Accuracy < 60%

### 失败案例分析

查看 `failures.json` 了解：
- 哪些类型的问题失败最多
- 系统回答与参考答案的差异
- LLM 评判的推理过程

## 常见问题

### Q: 评测需要多长时间？

A: 完整评测（10 个对话，约 150 个问题）需要：
- 评测运行：5-10 分钟
- LLM 评分：10-15 分钟（取决于 API 速度）
- 总计：15-25 分钟

### Q: 如何提高评测速度？

A: 
1. 使用 `--limit_conversations` 和 `--limit_questions` 限制规模
2. 减少 `--rate_limit_delay` 值（注意 API 限流）
3. 使用 `--no_llm` 跳过 LLM 评分（仅精确匹配）

### Q: LLM 评分和精确匹配有什么区别？

A:
- **精确匹配**: 只有字符串完全一致才算正确（严格但不智能）
- **LLM 评分**: 理解语义，允许改写（更接近人类评判）

例如：
- 参考答案："7 May 2023"
- 系统回答："May 7, 2023"
- 精确匹配：❌ 错误
- LLM 评分：✅ 正确

### Q: 如何调试失败的案例？

A:
1. 查看 `failures.json` 找到失败的问题 ID
2. 在 `detailed_scores.json` 中查看完整的评分信息
3. 检查 `model_outputs.json` 中的 `memories_used` 字段，看系统检索了哪些记忆
4. 使用 `backend/check_memory_status.py` 检查记忆是否正确存储

## 与其他评测的对比

| 评测 | 类型 | 问题数 | 特点 |
|------|------|--------|------|
| **LoCoMo** | 长期记忆 | ~150 | 多轮对话，时间跨度长 |
| **KnowMeBench** | 个性化记忆 | ~1000 | 个人信息，偏好理解 |

## 下一步

- 查看 `KNOWMEBENCH_EVAL_GUIDE.md` 了解 KnowMeBench 评测
- 阅读 `backend/docs/ARCHITECTURE.md` 了解系统架构
- 查看 `backend/OPTIMIZATION_STATUS.md` 了解性能优化

## 技术细节

### 数据集

- 位置：`data/locomo/locomo10.json`
- 格式：10 个长期对话，每个对话包含多个会话
- 问题：每个对话 10-20 个问题

### 评分算法

LLM 评判使用以下提示词模板：

```
You are an expert evaluator for long-term memory systems.

Question Type: {category_name}
Question: {question}
Reference Answer: {reference_answer}
Model Answer: {model_answer}

Evaluation Guidelines:
- For Factual Recall: Check if key facts match
- For Temporal Understanding: Check if dates/times are equivalent
- For Reasoning & Inference: Check if reasoning is sound
- For Detailed Understanding: Check if essential details are captured

Respond in JSON: {"correct": true/false, "confidence": 0.0-1.0, "reasoning": "..."}
```

### API 配置

默认使用 SiliconFlow 的 DeepSeek-V3：

```bash
OPENAI_API_KEY=<your_key>
OPENAI_API_BASE=https://api.siliconflow.cn/v1
OPENAI_MODEL=deepseek-ai/DeepSeek-V3
```

可以切换到其他 OpenAI 兼容的 API。

## 贡献

如果你发现评测有问题或有改进建议，欢迎：
1. 提交 Issue
2. 修改评测脚本
3. 添加新的评测指标

---

**最后更新**: 2026-01-26
