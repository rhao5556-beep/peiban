---
name: anthropics-skills-index
description: 快速集成 Anthropic 官方示例技能库（pdf、docx、pptx、xlsx、brand-guidelines 等）。用于选择并引用适配技能到项目或个人环境，统一触发与资源放置约定。
---

# Anthropic Skills 索引与集成

## 索引
- 官方技能库地址：https://github.com/anthropics/skills/tree/main/skills
- 常用类别举例：
  - 文档：docx、pdf、pptx、xlsx
  - 前端与设计：frontend-design、canvas-design、theme-factory
  - 协作：doc-coauthoring、internal-comms
  - 品牌：brand-guidelines
  - 构建与测试：webapp-testing、mcp-builder

## 集成方式（项目内手动）
- 复制目标技能的 SKILL.md 到本项目 skills/<vendor>/<skill-name>/SKILL.md
- 保持 YAML frontmatter 的 name/description 字段并根据项目场景补充描述触发条件
- 将长参考资料拆分到 references/ 下，脚本放 scripts/ 下，模板放 assets/ 下
- 在技能正文中明确何时读取各参考文件，以减少上下文占用

## 使用建议
- 与 brand-guidelines 协作：在输出需要品牌一致性的产物时触发该技能，统一颜色与字体
- 与 webapp-testing 协作：在前端/后端改动后，触发自动化测试与验收步骤
- 对大型文档技能（如 docx/pdf）：优先把 API 细节放 references/，正文仅保留核心流程与选择指南

## 验证与维护
- 触发描述必须清晰，避免含糊的“何时使用该技能”说明
- 引用的外部 API 或库版本需在 references/ 中注明，便于后续升级
- 每次新增脚本或模板后，补充使用示例与预期输出，确保可验证

