# OpenAI Evals（上游开源项目）

本仓库已以 vendor 方式引入 OpenAI 的开源评测框架（https://github.com/openai/evals），路径在：

- `external/openai-evals`

该目录包含 `oaieval` / `oaievalset` CLI 的源码，以及 `evals/registry`（大量 YAML + JSONL 数据集）。

## 快速验证（不安装）

在仓库根目录执行（让 Python 临时把 vendor 目录加入 `PYTHONPATH`）：

```bash
python -c "import sys, pathlib; sys.path.insert(0, str(pathlib.Path('external/openai-evals').resolve())); import evals; import evals.cli.oaieval as o; print('ok', o.__file__)"
```

## 说明

- OpenAI Evals 自身是一个独立 Python 包（包名：`evals`），其完整依赖在 `external/openai-evals/pyproject.toml`。
- 若要真正跑 `oaieval`，通常需要在一个隔离环境里安装该包及其依赖（依赖较多且较重）。

