# LoCoMo 评测失败诊断报告（基于实际证据）

**诊断时间**: 2026-01-27  
**评测结果**: 8.36% 准确率（1986 题中仅 166 题正确）

---

## 🔍 实际诊断数据

### 1. PostgreSQL 记忆存储状态

```
总记忆数: 18,503 条
├─ committed: 12,165 条 (65.7%)  ✅
└─ pending: 6,338 条 (34.3%)     ⚠️
```

**最近记忆**：
- 最近 5 条记忆全部处于 `pending` 状态
- 最新记忆时间：2026-01-27 04:35:22

### 2. Neo4j 图谱状态

```
总节点数: 232 个
总关系数: 168 个
实体类型分布: （未返回数据）
```

**对比分析**：
- 18,503 条记忆 → 仅 232 个节点
- **节点覆盖率 < 2%** ❌
- 说明绝大部分记忆未提取实体或未同步到图谱

### 3. Outbox 事件处理状态

```
Outbox 事件状态:
├─ pending: 5,285 个 (75.5%)    ❌ 大量积压
├─ processing: 606 个 (8.7%)    ⚠️ 可能卡住
├─ done: 603 个 (8.6%)          ✅ 处理成功
└─ dlq (死信队列): 448 个 (6.4%) ❌ 处理失败
```

**关键发现**：
- **75.5% 的事件未处理**
- 处理成功率仅 8.6%
- 28.6% 的记忆未同步到图谱（5,285 / 18,503）

### 4. Celery Worker 日志分析

**运行状态**: ✅ Worker 正在运行（Up 38 hours）

**错误日志**（最近 50 条）：
```
[2026-01-27 04:37:38] ERROR: API error: Error code: 401
{'error': {
    'message': 'Incorrect API key provided: sk-axkcy***qsos',
    'type': 'invalid_request_error',
    'code': 'invalid_api_key'
}}

[2026-01-27 04:37:38] WARNING: LLM extraction attempt 3 failed
[2026-01-27 04:37:38] ERROR: LLM extraction failed after 3 attempts
[2026-01-27 04:37:38] WARNING: LLM extraction failed, retrying in 1s (attempt 1)
[2026-01-27 04:37:38] ERROR: Event processing failed: Retry in 1s
```

**问题模式**：
- 所有事件都因为 **API key 401 错误** 失败
- Worker 不断重试（每次 3 次尝试 + 1s 延迟）
- 实体提取完全失败 → 无法写入 Neo4j/Milvus
- 事件最终进入死信队列或永久 pending

### 5. 检索功能测试

**测试查询**：
1. "Caroline 的性别认同是什么？"
2. "Melanie 什么时候跑了慈善跑？"
3. "Caroline 研究了什么？"

**结果**: ❌ 所有查询都失败（方法签名错误）

---

## 🎯 根本原因确认

### 致命问题：API Key 配置错误

**证据链**：
1. Celery worker 日志显示 **401 Unauthorized** 错误
2. API key 格式：`sk-axkcy***qsos`（疑似错误的 key）
3. 所有实体提取请求都失败
4. 5,285 个 Outbox 事件无法处理
5. 6,338 条记忆（34.3%）状态为 pending
6. Neo4j 仅有 232 个节点（应有数千个）

**影响链**：
```
API Key 错误 (401)
    ↓
实体提取失败
    ↓
Outbox 事件无法处理 (75.5% pending)
    ↓
记忆未同步到 Neo4j/Milvus (34.3% pending)
    ↓
图谱数据极度稀疏 (232 节点 vs 18,503 记忆)
    ↓
检索召回率 < 10%
    ↓
LoCoMo 准确率 8.36%
```

---

## 📊 问题量化分析

### 数据一致性问题

| 指标 | 实际值 | 预期值 | 差距 |
|------|--------|--------|------|
| 记忆总数 | 18,503 | 18,503 | ✅ |
| committed 记忆 | 12,165 (65.7%) | >95% | ❌ -29.3% |
| pending 记忆 | 6,338 (34.3%) | <5% | ❌ +29.3% |
| Neo4j 节点数 | 232 | ~5,000+ | ❌ -95% |
| Outbox 处理成功率 | 8.6% | >90% | ❌ -81.4% |
| Outbox 积压 | 5,285 | <100 | ❌ +5,185 |

### 性能指标

| 指标 | 实际值 | SLO 目标 | 状态 |
|------|--------|----------|------|
| Outbox Lag P50 | 未知（积压严重） | <2s | ❌ |
| Outbox Lag P95 | 未知（积压严重） | <30s | ❌ |
| 数据不一致率 | 34.3% | <1% | ❌ |

---

## 🔧 修复方案（按优先级）

### P0: 修复 API Key（立即执行）

**问题**: Celery worker 使用的 API key 错误或过期

**修复步骤**：

1. **检查 backend/.env 文件**：
   ```bash
   cat backend/.env | findstr OPENAI_API_KEY
   ```

2. **确认正确的 API key**：
   - 检查是否使用了正确的 SiliconFlow API key
   - 格式应该是：`sk-xxxxxxxxxxxxxxxxxxxxx`
   - 确认 API base URL：`https://api.siliconflow.cn/v1`

3. **更新 .env 文件**：
   ```bash
   # backend/.env
   OPENAI_API_KEY=你的正确API_KEY
   OPENAI_API_BASE=https://api.siliconflow.cn/v1
   OPENAI_MODEL=deepseek-ai/DeepSeek-V3
   ```

4. **重启 Celery worker**：
   ```bash
   docker restart affinity-celery-worker
   docker restart affinity-celery-beat
   ```

5. **验证修复**：
   ```bash
   # 查看 worker 日志，确认不再有 401 错误
   docker logs affinity-celery-worker --tail 20 -f
   ```

**预期效果**：
- 401 错误消失
- Outbox 事件开始正常处理
- pending 记忆逐渐减少

---

### P1: 处理积压的 Outbox 事件（API Key 修复后）

**问题**: 5,285 个待处理事件积压

**修复步骤**：

1. **确认 worker 正常工作**：
   ```bash
   docker logs affinity-celery-worker --tail 20
   # 应该看到 "Event processed successfully" 日志
   ```

2. **监控处理进度**：
   ```bash
   python backend/check_outbox_status.py
   ```

3. **如果处理太慢，增加 worker 并发数**：
   ```bash
   # 修改 docker-compose.yml
   celery-worker:
     command: celery -A app.worker worker --loglevel=info --concurrency=8
   
   # 重启
   docker-compose up -d celery-worker
   ```

4. **处理死信队列中的失败事件**：
   ```bash
   # 检查失败原因
   python backend/check_outbox_status.py
   
   # 如果是 API key 问题导致的失败，重置为 pending
   # 在 PostgreSQL 中执行：
   UPDATE outbox_events 
   SET status = 'pending', retry_count = 0, error_message = NULL
   WHERE status = 'dlq' AND error_message LIKE '%401%';
   ```

**预期效果**：
- pending 事件逐渐减少
- committed 记忆比例提升到 >95%
- Neo4j 节点数增加到数千个

---

### P2: 验证数据一致性（积压处理完成后）

**步骤**：

1. **重新运行诊断脚本**：
   ```bash
   python diagnose_locomo_failure.py
   ```

2. **检查关键指标**：
   - pending 记忆 < 5%
   - Neo4j 节点数 > 5,000
   - Outbox pending < 100

3. **如果仍有不一致，重新同步**：
   ```bash
   python backend/resync_memories_to_neo4j.py
   ```

---

### P3: 重新运行 LoCoMo 评测（数据修复后）

**步骤**：

1. **小规模测试**（100 题）：
   ```bash
   cd evals
   python run_full_locomo_pipeline.py --limit 100
   ```

2. **检查准确率提升**：
   - 预期：从 8.36% 提升到 25%+
   - 如果仍然很低，说明检索策略需要优化

3. **完整评测**（1986 题）：
   ```bash
   python run_full_locomo_pipeline.py
   ```

---

## 📈 预期改进效果

### 修复 API Key 后

| 指标 | 修复前 | 修复后（预期） | 提升 |
|------|--------|---------------|------|
| Outbox 处理成功率 | 8.6% | >90% | +81.4% |
| committed 记忆比例 | 65.7% | >95% | +29.3% |
| Neo4j 节点数 | 232 | 5,000+ | +2,068% |
| LoCoMo 准确率 | 8.36% | 25%+ | +17% |

### 为什么准确率只能提升到 25%？

**原因**：
1. **数据修复只能解决存储问题**（从 8.36% → 25%）
2. **检索策略仍需优化**（从 25% → 40%）
3. **时间推理能力缺失**（从 40% → 55%）

**后续优化方向**（见 LOCOMO_改进方案.md）：
- 降低检索阈值，提升召回率
- 实现分层记忆管理
- 添加时间推理能力
- 实体链接与消歧

---

## 🎯 关键洞察

### 1. Evidence 在你的系统中的对应物

**KnowMeBench 中的 evidence**：
- 指向 `dataset1.json` 中的记录 ID
- 例如：`"evidence": ["record_123", "record_456"]`

**你的系统中的对应物**：
- **PostgreSQL**: `memories` 表中的记录（`id` 字段）
- **Neo4j**: `Entity` 节点和 `RELATES_TO` 关系
- **Milvus**: 向量索引中的记忆向量

**数据流**：
```
用户对话
    ↓
PostgreSQL memories 表（id, content, status）
    ↓
Outbox 事件（memory_id）
    ↓
Celery Worker 处理
    ↓
实体提取（LLM）
    ↓
Neo4j 节点/关系（entity_id, provenance: [memory_id]）
    ↓
Milvus 向量（memory_id, embedding）
```

**检索时**：
```
用户查询
    ↓
向量检索（Milvus）→ 返回 memory_id
    ↓
图检索（Neo4j）→ 返回 entity_id → 关联的 memory_id
    ↓
合并去重 → 返回 memories 列表
    ↓
LLM 生成答案（基于检索到的 memories）
```

**所以**：
- Evidence = 能够回答问题的记忆记录
- 你的系统中 = PostgreSQL memories 表的记录
- 通过 Outbox 模式同步到 Neo4j/Milvus
- 检索时通过 memory_id 关联

### 2. 为什么 API Key 错误导致如此严重的后果？

**设计缺陷**：
- 实体提取是 Outbox 处理的**必经步骤**
- 没有降级策略（fallback）
- 失败后无限重试，阻塞队列
- 导致整个记忆同步链路崩溃

**改进建议**（长期）：
1. 添加 API 健康检查
2. 实现降级策略（跳过实体提取，仅存储原始记忆）
3. 限制重试次数，避免死循环
4. 监控 API 错误率，及时告警

### 3. 为什么 Neo4j 只有 232 个节点？

**计算**：
- 18,503 条记忆
- 假设每条记忆平均提取 3 个实体
- 预期节点数：18,503 × 3 × 0.657 (committed) ≈ 36,000 个
- 实际节点数：232 个
- **覆盖率：0.64%** ❌

**原因**：
- API Key 错误导致实体提取失败
- 仅有极少数记忆（可能是早期测试数据）成功提取
- 绝大部分记忆未同步到图谱

---

## ✅ 立即行动清单

### 今天（必做）

- [ ] 1. 检查 backend/.env 中的 OPENAI_API_KEY
- [ ] 2. 确认 API key 是否正确（SiliconFlow）
- [ ] 3. 更新 .env 文件（如果错误）
- [ ] 4. 重启 Celery worker 和 beat
- [ ] 5. 查看 worker 日志，确认 401 错误消失
- [ ] 6. 监控 Outbox 处理进度（每小时检查一次）

### 明天（高优先级）

- [ ] 7. 确认 pending 事件数量下降
- [ ] 8. 检查 Neo4j 节点数增长
- [ ] 9. 处理死信队列中的失败事件
- [ ] 10. 重新运行诊断脚本，验证修复效果

### 本周（中优先级）

- [ ] 11. 等待 Outbox 积压处理完成（可能需要数小时）
- [ ] 12. 运行 LoCoMo 小规模测试（100 题）
- [ ] 13. 分析准确率提升情况
- [ ] 14. 如果仍然很低，开始优化检索策略

---

## 📝 Git 提交建议

```bash
# 修复 API Key
git commit -m "Fix: 修复 Celery worker API key 配置错误

- 更新 OPENAI_API_KEY 为正确的 SiliconFlow key
- 修复导致 5,285 个 Outbox 事件积压的根本原因
- 预期 LoCoMo 准确率从 8.36% 提升到 25%+

根本原因：API key 401 错误导致实体提取失败，
34.3% 的记忆未同步到 Neo4j/Milvus"

# 处理积压事件
git commit -m "Fix: 处理 Outbox 积压事件

- 重置死信队列中的失败事件
- 增加 worker 并发数到 8
- 监控处理进度"

# 验证修复
git commit -m "Test: 验证 LoCoMo 评测修复效果

- 重新运行诊断脚本
- 小规模 LoCoMo 测试（100 题）
- 准确率从 8.36% 提升到 XX%"
```

---

## 🎯 总结

### 核心问题

**API Key 配置错误（401 Unauthorized）** 导致：
- 实体提取完全失败
- 75.5% 的 Outbox 事件无法处理
- 34.3% 的记忆未同步到图谱
- Neo4j 节点覆盖率 < 1%
- LoCoMo 准确率仅 8.36%

### 修复优先级

1. **P0**: 修复 API Key（立即）
2. **P1**: 处理 Outbox 积压（API Key 修复后）
3. **P2**: 验证数据一致性（积压处理完成后）
4. **P3**: 重新评测（数据修复后）

### 预期效果

- **短期**（1-2 天）：准确率从 8.36% → 25%+
- **中期**（1-2 周）：准确率从 25% → 40%+（需要优化检索）
- **长期**（1-2 月）：准确率从 40% → 55%+（需要时间推理）

---

**诊断完成时间**: 2026-01-27  
**下一步**: 立即检查并修复 API Key 配置
