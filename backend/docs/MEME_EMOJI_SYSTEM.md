# 表情包梗图系统文档

## 概述

表情包梗图系统使 AI 能够在对话中自然地使用流行的表情包和梗图。系统通过监控外部平台的热点内容、进行安全合规筛选、计算趋势分数，并基于用户好感度和对话上下文做出合适的使用决策。

## 架构

### 系统组件

1. **热点内容感知器** (`TrendingContentSensorService`)
   - 从外部平台获取热点内容（MVP：仅微博）
   - 提取表情包元数据
   - 计算内容哈希进行去重

2. **内容池管理器** (`ContentPoolManagerService`)
   - 管理表情包生命周期
   - 状态转换：候选 → 已批准/已拒绝 → 已归档
   - 查询和统计功能

3. **安全筛选器** (`SafetyScreenerService`)
   - 内容安全检查（暴力、色情、政治）
   - 文化敏感性检查
   - 法律合规检查
   - 伦理边界检查

4. **趋势分析器** (`TrendAnalyzerService`)
   - 计算趋势分数（0-100）
   - 确定趋势等级（新兴/上升/热门/巅峰/衰退）
   - 识别衰退表情包

5. **使用决策引擎** (`UsageDecisionEngineService`)
   - 基于好感度的频率控制
   - 上下文匹配
   - 情感适宜性检查
   - 多样性控制（24小时内不重复）

6. **使用历史服务** (`MemeUsageHistoryService`)
   - 记录表情包使用
   - 收集用户反馈
   - 计算接受率

### 数据流

#### 内容聚合流程（每1小时）

```
外部平台 API
    ↓
热点内容感知器（获取热点内容）
    ↓
内容哈希去重检查
    ↓
创建候选表情包记录
    ↓
安全筛选器（多层检查）
    ↓
更新状态（已批准/已拒绝/已标记）
    ↓
趋势分析器（计算初始分数）
```

#### 对话流程（实时）

```
用户消息
    ↓
对话服务生成基础回复
    ↓
检测情感基调
    ↓
使用决策引擎评估
    ├─ 查询好感度分数
    ├─ 匹配上下文
    ├─ 检查最近使用
    └─ 应用过滤规则
    ↓
选择表情包（或返回None）
    ↓
记录使用 + 增加计数
    ↓
返回响应（包含表情包或纯文本）
```

## API 端点

### GET /api/v1/memes/trending

获取热门表情包列表

**查询参数：**
- `limit`: 返回数量限制（默认20，最大100）

**响应：**
```json
{
  "memes": [
    {
      "id": "uuid",
      "image_url": "https://...",
      "text_description": "表情包描述",
      "source_platform": "weibo",
      "category": "humor",
      "trend_score": 85.5,
      "trend_level": "peak",
      "usage_count": 42
    }
  ],
  "total": 10
}
```

### POST /api/v1/memes/feedback

提交表情包反馈

**请求体：**
```json
{
  "usage_id": "uuid",
  "reaction": "liked"  // liked, ignored, disliked
}
```

### GET /api/v1/memes/stats

获取系统统计信息

**响应：**
```json
{
  "total_memes": 1000,
  "approved_memes": 800,
  "trending_memes": 50,
  "acceptance_rate": 0.75,
  "avg_trend_score": 65.5
}
```

### GET /api/v1/memes/preferences

获取用户表情包偏好

### PUT /api/v1/memes/preferences

更新用户表情包偏好

**查询参数：**
- `meme_enabled`: 是否启用表情包（true/false）

## 配置

### 环境变量

```bash
# 微博 API 配置
WEIBO_API_KEY=your-weibo-api-key
WEIBO_API_BASE_URL=https://api.weibo.com/2

# 安全筛选
MEME_SAFETY_SCREENING_ENABLED=true

# 聚合频率（小时）
MEME_SENSOR_INTERVAL_HOURS=1

# 趋势更新频率（小时）
MEME_TREND_UPDATE_INTERVAL_HOURS=2

# 归档阈值（天数）
MEME_ARCHIVAL_DECLINING_DAYS=30

# 去重检查
MEME_DUPLICATE_CHECK_ENABLED=true
```

### Celery 定时任务

1. **内容聚合** (`meme.aggregate_trending_memes`)
   - 频率：每1小时
   - 队列：meme
   - 功能：从平台获取热点内容并进行安全筛选

2. **趋势更新** (`meme.update_meme_scores`)
   - 频率：每2小时
   - 队列：meme
   - 功能：重新计算趋势分数并识别衰退表情包

3. **归档任务** (`meme.archive_old_memes`)
   - 频率：每日
   - 队列：maintenance
   - 功能：归档衰退超过30天的表情包

## 数据库表

### memes

表情包主表

**关键字段：**
- `id`: UUID 主键
- `text_description`: 文本描述（必需）
- `image_url`: 图片URL（MVP阶段可为空）
- `source_platform`: 来源平台
- `content_hash`: 内容哈希（用于去重，唯一）
- `status`: 生命周期状态
- `safety_status`: 安全状态
- `trend_score`: 趋势分数（0-100）
- `trend_level`: 趋势等级
- `usage_count`: 使用次数

### meme_usage_history

使用历史表

**关键字段：**
- `id`: UUID 主键
- `user_id`: 用户ID
- `meme_id`: 表情包ID
- `conversation_id`: 会话ID
- `used_at`: 使用时间
- `user_reaction`: 用户反应（liked/ignored/disliked）

### user_meme_preferences

用户偏好表

**关键字段：**
- `id`: UUID 主键
- `user_id`: 用户ID（唯一）
- `meme_enabled`: 是否启用表情包

## 监控

### 关键指标

1. **接受率** (`meme_usage_acceptance_rate`)
   - 目标：> 60%
   - 计算：喜欢数 / 总使用数

2. **安全筛选准确率** (`meme_safety_screening_accuracy`)
   - 目标：> 95%
   - 基于采样审核

3. **趋势检测延迟** (`meme_trend_detection_latency_seconds`)
   - 目标：P95 < 2小时
   - 从内容出现到可用的时间

4. **内容聚合成功率** (`meme_content_aggregation_success_rate`)
   - 目标：> 90%
   - 平台API调用成功率

5. **重复检测数** (`meme_duplicate_detected_total`)
   - 监控跨平台去重效果

### 告警规则

- 安全筛选准确率 < 95%
- 趋势检测延迟 P95 > 2小时
- 所有平台连续失败 > 2个周期
- 标记表情包队列 > 100项
- 接受率 < 60% 持续24小时
- 重复检测率 > 30%（可能表示API问题）

## 故障排除

### 常见问题

#### 1. 表情包不显示

**可能原因：**
- 用户选择退出（`meme_enabled=false`）
- 好感度分数过低（< 20）
- 没有合适的表情包匹配上下文
- 24小时内已使用过相同表情包

**排查步骤：**
1. 检查用户偏好设置
2. 查询用户好感度分数
3. 检查表情包池中的已批准表情包数量
4. 查看使用历史记录

#### 2. 内容聚合失败

**可能原因：**
- 微博API密钥无效或过期
- 网络连接问题
- API速率限制

**排查步骤：**
1. 检查环境变量 `WEIBO_API_KEY`
2. 查看Celery任务日志
3. 测试API连接
4. 检查速率限制状态

#### 3. 安全筛选过于严格

**可能原因：**
- 关键词黑名单过于宽泛
- 保守的筛选策略

**解决方案：**
1. 审查被拒绝的表情包
2. 调整关键词黑名单
3. 考虑使用"已标记"状态进行人工审核

## MVP 限制

当前MVP版本的限制：

1. **仅微博平台**：未来将支持抖音、B站等
2. **基于文本的安全筛选**：未来将使用ML模型进行图像分类
3. **无图片表情包**：仅支持文本和表情符号
4. **简单上下文匹配**：基于关键词，未来将使用语义相似度
5. **简化趋势评分**：基于平台热度分数和时间衰减

## 未来增强

### 阶段2（1-2周）

1. 图片表情包支持
2. 基于ML的图像安全检测
3. 语义相似度匹配（使用Milvus）
4. 用户反馈学习

### 阶段3（持续）

1. 多平台支持（B站、抖音）
2. 高级趋势评分公式
3. 个性化推荐
4. A/B测试框架

## 参考资料

- 设计文档：`.kiro/specs/meme-emoji-system/design.md`
- 需求文档：`.kiro/specs/meme-emoji-system/requirements.md`
- 任务列表：`.kiro/specs/meme-emoji-system/tasks.md`
- 快速入门：`backend/docs/MEME_EMOJI_QUICKSTART.md`
