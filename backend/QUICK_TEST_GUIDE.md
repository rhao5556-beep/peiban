# 对话质量优化 - 快速测试指南

## 🚀 立即测试

API 已重启，优化已生效。现在可以在前端（http://localhost:5173）测试以下场景：

---

## ✅ 测试场景 1：事实查询（核心改进）

### 测试步骤

1. 打开前端：http://localhost:5173
2. 发送消息：**"谁去沈阳旅游过"**

### 预期结果

- ✅ 路由到 Tier 1（DeepSeek-V3）
- ✅ 回复准确、自然（不再是模板化回复）
- ✅ 能正确理解问题并给出答案

### 优化前 vs 优化后

| 维度 | 优化前 | 优化后 |
|------|--------|--------|
| 路由 | Tier 3（7B） | Tier 1（DeepSeek-V3） |
| 回复 | 模板化、保守 | 准确、自然 |

---

## ✅ 测试场景 2：省略问句（核心改进）

### 测试步骤

1. 发送消息：**"我和二丫去了沈阳旅游"**
2. 等待 AI 回复
3. 发送消息：**"谁去了"**

### 预期结果

- ✅ AI 能理解"谁去了"指的是"谁去了沈阳"
- ✅ 回复："你和二丫"或类似的正确答案
- ✅ 不会说"我不记得"（因为刚刚说过）

### 优化前 vs 优化后

| 维度 | 优化前 | 优化后 |
|------|--------|--------|
| 理解 | ❌ 无法理解省略 | ✅ 能理解省略 |
| 回复 | "我不记得" | "你和二丫" |

---

## ✅ 测试场景 3：推理问句（高级功能）

### 测试步骤

1. 发送消息：**"昊哥住在大连"**
2. 等待 AI 回复
3. 发送消息：**"谁住海边"**

### 预期结果

- ✅ AI 能推理"大连是海边城市"
- ✅ 回复："昊哥住在大连，大连是海边城市，所以昊哥住海边"
- ✅ 展示常识推理能力

---

## ✅ 测试场景 4：简单问候（验证不受影响）

### 测试步骤

1. 发送消息：**"你好"**
2. 发送消息：**"早上好"**
3. 发送消息：**"谢谢"**

### 预期结果

- ✅ 仍然快速响应（< 500ms）
- ✅ 路由到 Tier 3（7B）
- ✅ 简单问候不受影响

---

## 📊 如何验证路由决策

### 方法 1：查看 API 日志

```bash
docker logs affinity-api --tail 50 -f
```

查找日志中的：
```
TierRouter: question + entity/location -> Tier 1 (fact query)
TierRouter: question detected -> Tier 2 (minimum)
TierRouter: simple message -> Tier 3
```

### 方法 2：查看响应时间

- Tier 1（DeepSeek-V3）：~2-3秒
- Tier 2（Qwen 14B）：~1-2秒
- Tier 3（Qwen 7B）：~0.5-1秒

---

## 🐛 如果遇到问题

### 问题 1：API 没有响应

**解决方案**：
```bash
# 检查 API 状态
docker ps | grep affinity-api

# 重启 API
docker restart affinity-api

# 查看日志
docker logs affinity-api --tail 50
```

### 问题 2：回复仍然"智障"

**可能原因**：
1. 记忆数据为空（Outbox 未处理）
2. LLM API 超时
3. 路由决策未生效

**排查步骤**：
```bash
# 1. 检查 Celery Worker 状态
docker logs affinity-celery-worker --tail 50

# 2. 检查 Outbox 处理状态
docker exec -it affinity-postgres psql -U affinity -d affinity -c "SELECT status, COUNT(*) FROM outbox_events GROUP BY status;"

# 3. 查看 API 日志确认路由
docker logs affinity-api --tail 50 -f
```

### 问题 3：前端显示"记忆中..."

**解决方案**：
```bash
# 检查 Celery Beat 是否运行
docker exec affinity-celery-worker ps aux | grep beat

# 如果没有运行，启动 Beat
docker exec -d affinity-celery-worker celery -A app.worker beat --loglevel=info
```

---

## 📈 预期改进效果

### 回复质量

- **事实查询**：准确率从 ~30% 提升到 ~80%
- **省略问句**：理解率从 ~10% 提升到 ~70%
- **自然度**：从"机械"提升到"自然"

### 路由分布

- **Tier 1 使用率**：从 ~10% 提升到 ~30%
- **Tier 2 使用率**：从 ~30% 提升到 ~50%
- **Tier 3 使用率**：从 ~60% 降低到 ~20%

---

## 🎯 下一步优化（可选）

如果第一阶段效果满意，可以继续实施：

### 优化 3：增加上下文窗口（5分钟）

```python
# 修改 backend/app/services/conversation_service.py
# 第 640 行
conversation_history = await self._get_conversation_history(session_id, limit=20)  # 从 5 改为 20

# 第 662 行
ranked_memories, ranked_facts = self.retrieval_service.unified_rerank(..., top_k=20)  # 从 10 改为 20
```

### 优化 4：自然语言化检索结果（30分钟）

实现 `_format_memories_naturally()` 方法，将结构化数据转换为自然语言。

---

## 📞 需要帮助？

如果测试过程中遇到任何问题，可以：

1. 查看日志：`docker logs affinity-api --tail 100`
2. 查看测试脚本：`backend/test_routing_optimization.py`
3. 查看完整文档：`backend/OPTIMIZATION_STATUS.md`

---

**祝测试顺利！🎉**
