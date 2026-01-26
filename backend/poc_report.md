# PoC 实验报告: Hybrid vs Baseline Retrieval

## 实验目标

验证 Hybrid Retrieval (Vector + Graph) 相比纯向量检索的效果提升。

**目标**: Recall@10 提升 ≥ 15%

## 实验配置

- **测试数据集**: 20 用户 × 10 轮对话 (模拟真实场景)
- **测试查询数**: 52
- **评估指标**: Recall@10, Recall@5, MRR, NDCG@10, P50/P95 Latency
- **Hybrid 参数**: α=0.6 (向量权重), 图扩展 1-hop

## 方法说明

### Baseline (Vector Only)
- 纯向量相似度检索
- 使用余弦相似度排序

### Hybrid (Vector + Graph)
- 四因子融合:
  1. Vector similarity (60%)
  2. Graph expansion score (40%)
  3. Entity overlap bonus
  4. Recency score

## 结果对比

| 指标 | Baseline | Hybrid | 提升 |
|------|----------|--------|------|
| **Recall@10** | 0.0256 | 0.2756 | **+975.00%** |
| Recall@5 | 0.0256 | 0.1603 | +525.00% |
| MRR | 0.0205 | 0.3023 | +1373.92% |
| NDCG@10 | 0.0160 | 0.2064 | +1189.64% |
| P50 Latency | 13.26ms | 11.81ms | - |
| P95 Latency | 16.67ms | 18.07ms | - |

## 分析

### 效果提升原因

1. **实体关联**: Graph expansion 能够找到与查询实体直接相关的记忆，即使向量相似度不高
2. **语义补充**: 图结构捕获了实体间的关系，补充了向量空间的语义信息
3. **时间感知**: Recency score 使近期记忆获得适当加成

### 延迟分析

- Hybrid 方法增加了图扩展步骤，P95 延迟略有增加
- 但仍在可接受范围内 (< 100ms)

## 结论

✅ **目标达成**: Hybrid Retrieval Recall@10 提升 975.00% ≥ 15%

## 决策建议

**采纳 Hybrid Retrieval 方案**


---
**实验时间**: 2025-12-30 11:53:18
**数据集规模**: 52 queries, ~260 memories
