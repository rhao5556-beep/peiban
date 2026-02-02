# 评测运行指引（Runbook）

## 禁止清单
- 不要在 PowerShell 里直接粘贴/执行多行 Python 语句
- 不要使用 `python -c` 执行多行代码，或包含 JSON/字典/大括号/嵌套引号的复杂字符串

## 正确路径
- 环境预检（强制）：
  - `python tools/check_eval_env.py`
- LoCoMo：
  - `python evals/run_full_locomo_pipeline.py --backend_url http://localhost:8000 --mode hybrid`
- KnowMeBench（dataset1）：
  - `python evals/run_knowmebench_dataset1_pipeline.py --backend_base_url http://localhost:8000 --mode graph_only --limit_per_task 3`
- 如需跳过预检（不推荐）：
  - 追加 `--skip_env_check`

## 故障速查
- 10（key missing）：未设置 OPENAI_API_KEY
- 20（auth failed）：鉴权失败（401/403）
- 30（api base bad）：Base 错误/404
- 40（network）：网络/超时
- 50（dep missing）：依赖缺失（如 requests）

## 小贴士
- 只跑一小批题目验证链路：LoCoMo 用 `--limit_conversations/--limit_questions`；KnowMeBench 用 `--limit_per_task`
- 真实 LLM Judge 走环境变量：OPENAI_API_KEY / OPENAI_API_BASE / OPENAI_MODEL（默认 SiliconFlow DeepSeek-V3）
