# KnowMeBench（独立评测项目）

本目录用于把 KnowMeBench 的题库跑在“陪伴项目后端 API”上，属于独立评测项目；它与 `evals/`（原版 OpenAI Evals 对照/兼容入口）分离。

## 依赖

- KnowMeBench 子模块：`external/KnowMeBench`
- 后端服务：默认 `http://localhost:8000`
- 可选 Judge：OpenAI 兼容 API（用于对 `model_answer` 打分）

## Dataset1：生成模型输出

运行：

- `python affinity_evals/knowmebench/run_dataset1_pipeline.py --backend_base_url http://localhost:8000 --mode graph_only --eval_mode --concurrency 6`

默认会把产物写到 `outputs/knowmebench_run/ds1_pipeline_<mode>_<timestamp>/`：

- `*.model_outputs.json`
- `merged_for_official_eval.json`

## Judge：对模型输出打分

运行：

- `python affinity_evals/knowmebench/official_judge.py --input_dir <上一步产物目录> --output_file <输出 json>`

## 合并产物（可选）

- `python affinity_evals/knowmebench/merge_outputs.py --input_dir <目录> --output_file <merged_for_official_eval.json>`
