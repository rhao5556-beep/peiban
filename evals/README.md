# Evals（本仓库内置评测）

## 目的

- 对正在运行的后端（默认 `http://localhost:8010`）发起一组固定用例请求
- 可选使用 OpenAI 兼容 API（如硅基流动）作为 “Judge” 对输出做二分类打分（0/1）

## 配置

复制并填写本目录下的 `.env.local`（或参考 `.env.example`）：

- `OPENAI_API_KEY`：OpenAI 兼容 API Key（仅在启用 Judge 时需要；本项目默认使用硅基流动）
- `OPENAI_BASE_URL`：OpenAI 兼容 Base URL（例如硅基流动：`https://api.siliconflow.cn/v1`）
- `AFFINITY_EVAL_OPENAI_API_KEY`：用于评测裁判/基线的 Key（推荐用这个，避免和后端的 Key 冲突）
- `AFFINITY_EVAL_OPENAI_BASE_URL`：用于评测裁判/基线的 Base URL（例如 `https://api.siliconflow.cn/v1`）
- `AFFINITY_EVAL_BACKEND_BASE_URL`：后端地址（默认 `http://localhost:8010`）
- `AFFINITY_EVAL_ENABLE_JUDGE`：`1` 开启 Judge；没有 key 会自动降级为关闭
- `AFFINITY_EVAL_JUDGE_MODEL`：Judge 使用的模型（建议填硅基流动可用的模型，例如 `Pro/deepseek-ai/DeepSeek-V3`）
- `AFFINITY_EVAL_BASELINE_MODEL`：pairwise 基线模型（默认同 Judge）

`evals/.gitignore` 已忽略 `.env.local`，避免密钥被误提交。

## 运行

确保后端已启动后运行：

```bash
python evals/run_affinity_evals.py
```

只跑某个评测：

```bash
python evals/run_affinity_evals.py --eval affinity_short_term_recall
```

输出会写入 `evals/reports/`（report + meta + jsonl）。

## 关于 knowmebench

- 生成模型输出：`python evals/run_knowmebench_dataset1_pipeline.py`（输出到 `outputs/knowmebench_run/`）
- 运行官方 Judge：`python evals/run_knowmebench_official_judge.py --input_dir <输出目录>`
