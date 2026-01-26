---
name: superpowers-workflow
description: 统一接入 obra/superpowers 的工程工作流：交互式设计、详细实现计划、并行子代理执行、TDD、代码评审与 git worktrees。用于需要强流程与验证的开发任务。
---

# Superpowers（工程工作流封装）

## 安装（Claude Code 插件市场）

```bash
/plugin marketplace add obra/superpowers-marketplace
/plugin install superpowers@superpowers-marketplace
```

安装后可用的核心命令：
- /superpowers:brainstorm → 交互式设计细化与方案备忘
- /superpowers:write-plan → 生成可执行的详细实施计划（含验证步骤）
- /superpowers:execute-plan → 批量执行计划并设定人工检查点

## 基本工作流
- 设计阶段（brainstorming）：
  - 在写代码前触发，澄清目标、探索替代方案、分节呈现设计并保存设计文档
- 隔离开发环境（using-git-worktrees）：
  - 创建独立 worktree/分支、跑项目初始化并验证测试基线为“绿色”
- 计划编写（writing-plans）：
  - 将工作拆分为 2–5 分钟任务；每个任务包含精确文件路径、完整代码与验证步骤
- 执行实现（subagent-driven-development / executing-plans）：
  - 为每个任务派生子代理，先对齐规格后做代码质量检查；或批量执行并在关键节点人工检视
- 测试驱动开发（test-driven-development）：
  - RED-GREEN-REFACTOR：先写失败测试→写最小实现→看测试转绿→再重构；删除先于测试编写的代码
- 代码评审（requesting-code-review / receiving-code-review）：
  - 计划一致性检查与质量问题分级；关键问题阻断继续推进
- 收尾（finishing-a-development-branch）：
  - 验证测试、呈现合并/PR/保留/丢弃选项并清理工作树

## 使用建议
- 当任务风险高或易跑偏时，优先用 brainstorm → write-plan → execute-plan 的闭环
- 与 Planning with Files 协同：将设计/计划摘要写入 task_plan.md；验证输出写入 progress.md
- 在 Windows/本地环境使用时，避免交互式命令长时间占用终端，按批次执行

## 验证与完成
- 每个任务自带的验证步骤必须执行并记录结论
- 在宣告完成前，确保测试全绿、设计文档与计划状态同步更新

