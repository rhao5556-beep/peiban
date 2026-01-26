---
name: planning-with-files
description: 持久化三文件规划（task_plan.md、findings.md、progress.md）与会话恢复的工作流。用于复杂任务的规划、研究、进度记录与完成验证；支持 Windows 与 Claude Code 手动/插件模式。
---

# Planning with Files（三文件持久化规划）

## 快速安装（Claude Code 插件模式）

```powershell
# 注册并安装（Windows）
claude plugins install OthmanAdi/planning-with-files
Copy-Item -Recurse -Path "$env:USERPROFILE\.claude\plugins\cache\planning-with-files\planning-with-files\*\skills\planning-with-files" -Destination "$env:USERPROFILE\.claude\skills\"
# 重启 Claude Code 后可用：/planning-with-files
```

不使用插件时，可直接采用本技能的流程指引在项目内创建三文件并遵循下述工作流。

## 工作流（五步）
- 初始化：在任务开始前创建三文件，建议放在项目根或 docs/planning/
  - task_plan.md → 任务分期与里程碑
  - findings.md → 研究与事实证据
  - progress.md → 会话日志与测试结果
- 决策前复读（PreToolUse）：做出重要决策前，先重读 task_plan.md 与 findings.md 以避免目标漂移
- 写操作后记录（PostToolUse）：每次文件写入或重要操作后，更新 progress.md 并记录验证结果
- 错误与重试：将失败原因与修复策略写入 findings.md，避免重复犯错
- 完成验证（Stop Hook）：在宣告完成前，检查三文件的状态是否满足目标与测试通过

## 手动使用指引
- 触发建议：当任务包含≥3个步骤、需要跨会话持续推进或可能发生目标漂移时
- 文件命名：推荐 task_plan.md / findings.md / progress.md，亦可按模块拆分：planning/<feature>/...
- 验证实践：
  - 为每个阶段在 task_plan.md 写下“完成标准”
  - 在 progress.md 记录测试命令、输出摘要与结论
  - 将外部资料与关键结论存入 findings.md 并标注来源

## 与本项目集成
- 在项目根创建 docs/planning/ 或 planning/ 目录
- 开始复杂任务前先写入三文件并作为唯一“权威记忆”，避免把重要事项仅留在对话上下文
- 在代码评审或阶段验收时，以三文件作为证据链与验收材料

## 维护建议
- 保持描述简洁：只写对后续决策有价值的信息
- 定期归档：完成一个里程碑后，进度日志截断进 archive/，保留最新窗口
- 避免重复：把详尽资料放 findings.md，task_plan.md 只保留阶段计划与完成标准

