# KnowMeBench 评测 - 快速开始

## ✅ 你的系统已就绪

- ✅ 后端服务运行中（http://localhost:8000）
- ✅ LLM API 配置完成（硅基流动 DeepSeek-V3）
- ✅ Judge 模型配置完成
- ✅ KnowMeBench 数据集已安装

## 🚀 三步开始评测

### 方式一：使用快捷脚本（推荐）

#### 1. 快速测试（每个任务 3 题，约 5 分钟）
```bash
run_knowmebench_eval.bat quick
```

#### 2. 完整评测（所有题目，约 30-60 分钟）
```bash
run_knowmebench_eval.bat full
```

#### 3. 运行 Judge 评分
```bash
run_knowmebench_eval.bat judge
```

### 方式二：手动运行

#### 1. 快速测试
```bash
python affinity_evals/knowmebench/run_dataset1_pipeline.py --backend_base_url http://localhost:8000 --mode graph_only --eval_mode --limit_per_task 3 --concurrency 4
```

#### 2. 完整评测
```bash
python affinity_evals/knowmebench/run_dataset1_pipeline.py --backend_base_url http://localhost:8000 --mode graph_only --eval_mode --concurrency 6
```

#### 3. Judge 评分（替换 <timestamp> 为实际时间戳）
```bash
python affinity_evals/knowmebench/official_judge.py --input_dir outputs/knowmebench_run/ds1_pipeline_graph_only_<timestamp> --output_file outputs/knowmebench_run/ds1_pipeline_graph_only_<timestamp>/judge_results.json --concurrency 4
```

## 📊 评测内容

KnowMeBench 包含 7 种任务类型，评测 AI 的长期记忆能力：

1. **Information Extraction** - 信息抽取
2. **Adversarial Abstention** - 对抗性克制（识别陷阱问题）
3. **Temporal Reasoning** - 时间推理
4. **Logical Event Ordering** - 逻辑事件排序
5. **Mnestic Trigger Analysis** - 记忆触发分析
6. **Mind-Body Interaction** - 心身交互
7. **Expert-Annotated Psychoanalysis** - 专家标注心理分析

## 📈 查看结果

### 查看模型输出
```bash
# 输出目录会在评测完成后打印
# 例如：outputs/knowmebench_run/ds1_pipeline_graph_only_20260126_150000/

# 查看某个任务的输出
type outputs\knowmebench_run\ds1_pipeline_graph_only_<timestamp>\knowmebench.dataset1.information_extraction.<timestamp>.model_outputs.json
```

### 查看 Judge 评分
```bash
type outputs\knowmebench_run\ds1_pipeline_graph_only_<timestamp>\judge_results.json
```

评分标准（0-5 分）：
- **5 分**：完全正确，无编造
- **3 分**：部分正确或轻微偏差
- **1 分**：大部分错误或明显编造
- **0 分**：严重编造或与参考答案相反

## 🎯 预期结果

根据你的系统配置（graph_only 模式），预期表现：

- **Information Extraction**: 3-4 分（依赖图检索准确性）
- **Adversarial Abstention**: 4-5 分（系统应能正确拒答）
- **Temporal Reasoning**: 3-4 分（时间推理能力）
- **其他任务**: 2-4 分（取决于记忆图谱质量）

**平均分目标**: 3.0-4.0 分

## ⚠️ 注意事项

1. **首次运行建议使用快速测试**（`quick` 模式），验证流程正常
2. **完整评测需要 30-60 分钟**，请确保网络稳定
3. **Judge 评分会调用 LLM API**，会产生额外的 API 费用
4. **并发数不要设置过高**，避免触发 API 限流（建议 4-6）

## 🔧 故障排查

### 后端连接失败
```bash
# 检查后端服务
curl http://localhost:8000/api/v1/health

# 如果失败，重启后端
cd backend
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### API 限流错误
- 降低并发数：`--concurrency 2`
- 等待一段时间后重试

### Judge 评分失败
- 检查 `evals/.env.local` 中的 API Key 是否正确
- 确认 API 额度充足

## 📚 详细文档

完整文档请查看：`KNOWMEBENCH_EVAL_GUIDE.md`

## 🎉 开始评测

现在就可以开始了！建议先运行快速测试：

```bash
run_knowmebench_eval.bat quick
```

评测完成后，系统会打印输出目录路径，然后运行：

```bash
run_knowmebench_eval.bat judge
```

祝评测顺利！🚀
