# MVP 验收清单

## 使用说明
请按照以下清单逐项验证 MVP 功能。每完成一项，在 `[ ]` 中填入 `x`。

---

## 1. 环境准备

- [ ] Docker 和 Docker Compose 已安装
- [ ] 后端服务正常运行（PostgreSQL, Neo4j, Redis, Milvus）
- [ ] Celery worker 和 beat 正常运行
- [ ] 前端开发服务器已启动

验证命令：
```bash
docker-compose ps
# 应该看到所有服务状态为 Up
```

---

## 2. 数据库迁移

- [ ] 执行迁移脚本成功
- [ ] 三张表已创建（content_library, user_content_preference, recommendation_history）
- [ ] 索引已创建

验证命令：
```bash
docker exec -it affinity-postgres psql -U affinity -d affinity -c "\dt content*"
docker exec -it affinity-postgres psql -U affinity -d affinity -c "\d content_library"
```

预期输出：应该看到三张表的定义

---

## 3. Celery 任务注册

- [ ] 内容抓取任务已注册
- [ ] 内容清理任务已注册
- [ ] 推荐生成任务已注册

验证命令：
```bash
docker exec affinity-celery-worker celery -A app.worker inspect registered | grep content
```

预期输出：
```
app.worker.tasks.content_aggregation.fetch_daily_content
app.worker.tasks.content_aggregation.cleanup_old_content
app.worker.tasks.content_recommendation.generate_daily_recommendations
```

---

## 4. 内容抓取

- [ ] 手动触发抓取任务成功
- [ ] 内容库有数据
- [ ] 内容包含标题、摘要、URL、标签
- [ ] 嵌入向量已生成（1024 维）

验证命令：
```bash
# 触发抓取
docker exec affinity-celery-worker celery -A app.worker call app.worker.tasks.content_aggregation.fetch_daily_content

# 等待 30-60 秒后检查
docker exec -it affinity-postgres psql -U affinity -d affinity -c "SELECT COUNT(*), source FROM content_library GROUP BY source;"
docker exec -it affinity-postgres psql -U affinity -d affinity -c "SELECT title, source, array_length(tags, 1) as tag_count FROM content_library LIMIT 3;"
```

预期输出：应该看到至少几条 RSS 内容

---

## 5. 用户好感度

- [ ] 测试用户好感度 ≥ 40（friend 状态）
- [ ] 如果不足，已通过对话或手动调整提升

验证命令（需要先获取 token）：
```bash
# 获取 token
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/token -H "Content-Type: application/json" -d '{}' | jq -r '.access_token')

# 查看好感度历史
curl -s -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/v1/affinity/history | jq '.[-1]'
```

预期输出：`new_score` 应该 ≥ 0.4（对应 40 分）

---

## 6. 用户偏好设置

### 6.1 通过 API 设置

- [ ] 成功启用推荐功能
- [ ] 成功设置每日限额
- [ ] 成功获取偏好设置

验证命令：
```bash
# 启用推荐
curl -s -X PUT http://localhost:8000/api/v1/content/preference \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"enabled": true, "daily_limit": 3}' | jq

# 获取偏好
curl -s -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/v1/content/preference | jq
```

预期输出：`enabled: true`, `daily_limit: 3`

### 6.2 通过前端设置

- [ ] 前端能打开"内容推荐"标签
- [ ] 能看到"推荐设置"区域
- [ ] 能切换启用开关
- [ ] 能选择每日限额
- [ ] 能选择来源
- [ ] 能设置免打扰时间
- [ ] 点击"保存设置"成功

---

## 7. 推荐生成

- [ ] 手动触发推荐生成成功
- [ ] 推荐历史表有数据
- [ ] 推荐数量符合每日限额
- [ ] 推荐内容多样性符合要求

验证命令：
```bash
# 触发推荐生成
docker exec affinity-celery-worker celery -A app.worker call app.worker.tasks.content_recommendation.generate_daily_recommendations

# 等待几秒后检查
docker exec -it affinity-postgres psql -U affinity -d affinity -c "SELECT COUNT(*) FROM recommendation_history WHERE recommended_at >= CURRENT_DATE;"
docker exec -it affinity-postgres psql -U affinity -d affinity -c "SELECT title, source, match_score, rank_position FROM recommendation_history rh JOIN content_library cl ON rh.content_id = cl.id WHERE recommended_at >= CURRENT_DATE ORDER BY rank_position;"
```

预期输出：应该看到 1-3 条推荐记录

---

## 8. API 端点测试

### 8.1 获取推荐

- [ ] API 返回今日推荐
- [ ] 推荐包含标题、摘要、URL、来源、标签
- [ ] 推荐按排名排序

验证命令：
```bash
curl -s -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/v1/content/recommendations | jq
```

### 8.2 提交反馈

- [ ] 能提交 clicked 反馈
- [ ] 能提交 liked 反馈
- [ ] 能提交 disliked 反馈
- [ ] 反馈已记录到数据库

验证命令：
```bash
# 获取推荐 ID
REC_ID=$(curl -s -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/v1/content/recommendations | jq -r '.[0].id')

# 提交点击反馈
curl -s -X POST http://localhost:8000/api/v1/content/recommendations/$REC_ID/feedback \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"action": "clicked"}' | jq

# 检查反馈
docker exec -it affinity-postgres psql -U affinity -d affinity -c "SELECT id, clicked_at, feedback FROM recommendation_history WHERE id = '$REC_ID';"
```

---

## 9. 前端功能测试

### 9.1 推荐展示

- [ ] 能看到"今日推荐"区域
- [ ] 显示推荐标题、来源、摘要
- [ ] 显示标签（最多 3 个）
- [ ] 显示匹配分数
- [ ] 点击标题能在新标签页打开链接
- [ ] 链接使用 `noopener noreferrer`
- [ ] 点击后显示"已查看"标记

### 9.2 反馈按钮

- [ ] 能看到"喜欢"按钮
- [ ] 能看到"不感兴趣"按钮
- [ ] 点击"喜欢"后按钮变为选中状态
- [ ] 点击"不感兴趣"后推荐从列表移除

### 9.3 加载状态

- [ ] 加载时显示 loading 动画
- [ ] 错误时显示错误信息
- [ ] 无推荐时显示提示信息

### 9.4 偏好设置

- [ ] 能看到"推荐设置"区域
- [ ] 启用开关能正常切换
- [ ] 每日限额选择器能正常工作
- [ ] 来源多选框能正常工作
- [ ] 免打扰时间能正常设置
- [ ] 点击"保存设置"后显示成功提示

---

## 10. MVP 验证脚本

- [ ] 运行验证脚本成功
- [ ] 所有测试通过
- [ ] 无错误输出

验证命令：
```bash
cd backend
python test_content_recommendation_mvp.py
```

预期输出：
```
总计: 6 通过, 0 失败, 0 跳过
🎉 MVP 功能验证通过！
```

---

## 11. 业务规则验证

- [ ] stranger 状态用户不会收到推荐
- [ ] friend+ 状态用户能收到推荐
- [ ] 推荐默认关闭（新用户）
- [ ] 每日限额生效（不超过设定值）
- [ ] 同一来源最多 1 条
- [ ] 同一话题最多 2 条
- [ ] 30 天内推荐过的内容不会重复推荐

---

## 12. 性能验证

- [ ] RSS 抓取 < 5 分钟
- [ ] 推荐生成 < 3 秒（单用户）
- [ ] API 响应 < 500ms

验证方法：
- 查看 Celery 日志中的任务执行时间
- 使用 `time` 命令测量 API 响应时间

---

## 13. 文档验证

- [ ] 已阅读完整文档（`backend/docs/CONTENT_RECOMMENDATION.md`）
- [ ] 已阅读快速开始指南（`backend/docs/CONTENT_RECOMMENDATION_QUICKSTART.md`）
- [ ] 已阅读 MVP 完成总结（`.kiro/specs/content-recommendation/MVP_COMPLETION_SUMMARY.md`）
- [ ] 文档内容清晰易懂
- [ ] 示例代码可以正常运行

---

## 14. 代码质量验证

- [ ] 无 TypeScript 编译错误
- [ ] 无 Python 语法错误
- [ ] 代码遵循项目命名规范
- [ ] 代码注释完整
- [ ] 无明显的代码异味

验证命令：
```bash
# 前端类型检查
cd frontend
npm run build

# 后端语法检查
cd backend
python -m py_compile app/services/content_recommendation_service.py
python -m py_compile app/services/content_aggregator_service.py
```

---

## 15. 集成验证

- [ ] Celery 任务能正常调度
- [ ] API 端点能正常访问
- [ ] 前端能正常调用后端 API
- [ ] 数据能正常写入数据库
- [ ] 向量搜索能正常工作

---

## 验收结果

### 通过项数：_____ / 60

### 整体评价：
- [ ] 优秀（55-60 项通过）
- [ ] 良好（50-54 项通过）
- [ ] 合格（45-49 项通过）
- [ ] 需要改进（< 45 项通过）

### 发现的问题：
1. 
2. 
3. 

### 改进建议：
1. 
2. 
3. 

### 下一步计划：
- [ ] 立即进入阶段 2（增强功能）
- [ ] 收集用户反馈后再决定
- [ ] 优化 MVP 功能
- [ ] 其他：__________

---

## 签字确认

验收人：__________  
验收日期：__________  
验收结果：[ ] 通过  [ ] 不通过

备注：
