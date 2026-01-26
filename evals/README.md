# evals（目录说明）

## 目的

- 本目录用于放置与“评测框架对照/兼容入口”相关的内容
- 项目内的评测实现已迁移到 `affinity_evals/`，其中 KnowMeBench 是独立评测项目：`affinity_evals/knowmebench/`

## 关于 OpenAI Evals（原版）

为便于对照与复原，已将原版仓库作为子模块引入到：

- `external/openai-evals`（对应开源地址 `https://github.com/openai/evals.git`）

如需运行原版 OpenAI Evals，请参考该目录下的 `README.md` / `docs/run-evals.md`；原版 registry 数据使用 Git-LFS 管理，若需要完整数据集请在本机安装 Git-LFS 后再拉取。

## 配置

如需使用 OpenAI 兼容 API（例如作为 Judge），复制并填写本目录下的 `.env.local`（或参考 `.env.example`）：

- `OPENAI_API_KEY`：OpenAI 兼容 API Key（仅在启用 Judge 时需要；本项目默认使用硅基流动）
- `OPENAI_BASE_URL`：OpenAI 兼容 Base URL（例如硅基流动：`https://api.siliconflow.cn/v1`）
- `AFFINITY_EVAL_OPENAI_API_KEY`：用于评测裁判/基线的 Key（推荐用这个，避免和后端的 Key 冲突）
- `AFFINITY_EVAL_OPENAI_BASE_URL`：用于评测裁判/基线的 Base URL（例如 `https://api.siliconflow.cn/v1`）
- `AFFINITY_EVAL_BACKEND_BASE_URL`：后端地址（默认 `http://localhost:8000`）
- `AFFINITY_EVAL_ENABLE_JUDGE`：`1` 开启 Judge；没有 key 会自动降级为关闭
- `AFFINITY_EVAL_JUDGE_MODEL`：Judge 使用的模型（建议填硅基流动可用的模型，例如 `deepseek-ai/DeepSeek-V3`）
- `AFFINITY_EVAL_BASELINE_MODEL`：pairwise 基线模型（默认同 Judge）

`evals/.gitignore` 已忽略 `.env.local`，避免密钥被误提交。

## 运行

实际评测入口位于：

- KnowMeBench：`affinity_evals/knowmebench/README.md`

为兼容历史命令，本目录仍保留 3 个 shim 脚本（转发到新位置）：

- `run_knowmebench_dataset1_pipeline.py`
- `knowmebench_official_judge.py`
- `merge_knowmebench_outputs.py`

## 关于 knowmebench

KnowMeBench 的评测脚本已迁移至 `affinity_evals/knowmebench/`；历史运行产物位于 `outputs/knowmebench_run/`。
