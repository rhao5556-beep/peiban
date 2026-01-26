# 原版 OpenAI Evals（对照用）

本仓库的 `evals/` 目录主要用于评测“陪伴项目后端 API 的系统行为”（带自定义 Judge / 产物格式），属于改造版脚本集合。

为了便于对照与复原，已把原版开源仓库 `openai/evals` 作为子模块引入到：

- `external/openai-evals`

## 快速使用（原版）

在需要运行原版框架的 Python 环境中：

1. 安装（开发模式）：
   - `pip install -e external/openai-evals`
2. 按原版文档配置 `OPENAI_API_KEY` 等环境变量
3. 参考原版文档运行：
   - `external/openai-evals/docs/run-evals.md`

注意：原版 registry 数据使用 Git-LFS 管理；若你需要完整数据集，请安装 Git-LFS 后在 `external/openai-evals` 目录内执行其文档中的 `git lfs fetch/pull`。

## 本仓库改造点（与原版的主要差异）

- 评测目标：原版以“模型 completion 行为”为主；本仓库脚本以“后端 API 行为”为主（`backend_base_url` 等参数）。
- Judge：本仓库 Judge 走 OpenAI 兼容 Chat Completions，并要求输出严格 JSON `{score, reasoning}`；原版支持多种 eval template / completion fn / registry 机制。

