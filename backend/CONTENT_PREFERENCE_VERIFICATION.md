# 内容推荐偏好设置 - 验证清单

## 后端 API 验证 ✅

### 1. 获取偏好设置
```bash
curl -X GET "http://localhost:8000/api/v1/content/preference" \
  -H "Authorization: Bearer <token>"
```
**预期结果**: 200 OK，返回当前偏好设置

### 2. 更新所有字段
```bash
curl -X PUT "http://localhost:8000/api/v1/content/preference" \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "content_recommendation_enabled": true,
    "max_daily_recommendations": 5,
    "preferred_sources": ["bilibili", "zhihu", "weibo", "rss"],
    "excluded_topics": ["politics"],
    "quiet_hours_start": "22:00",
    "quiet_hours_end": "08:00"
  }'
```
**预期结果**: 200 OK，所有字段正确保存

### 3. 时间字段转换
- ✅ 输入 `"22:00"` → 数据库存储 `time(22, 0)` → 返回 `"22:00:00"`
- ✅ 边界值 `"00:00"` 和 `"23:59"` 正常工作
- ✅ 无效格式返回 400 错误

### 4. 部分更新
```bash
curl -X PUT "http://localhost:8000/api/v1/content/preference" \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"max_daily_recommendations": 3}'
```
**预期结果**: 200 OK，只更新指定字段，其他字段保持不变

## 前端 UI 验证 📋

### 访问地址
http://localhost:5174

### 验证步骤

1. **打开推荐设置页面**
   - [ ] 页面正常加载
   - [ ] 所有控件显示正确

2. **主开关测试**
   - [ ] 关闭状态：所有子控件灰色禁用
   - [ ] 开启状态：所有子控件可编辑
   - [ ] 状态提示文字正确显示

3. **每日推荐数量**
   - [ ] 滑块可拖动（1-10）
   - [ ] 数字显示正确

4. **内容来源选择**
   - [ ] 可多选：B站、知乎、微博、RSS
   - [ ] 选中状态正确显示

5. **免打扰时段**
   - [ ] 开始时间选择器正常
   - [ ] 结束时间选择器正常
   - [ ] 时间格式 HH:MM

6. **保存设置**
   - [ ] 点击"保存设置"按钮
   - [ ] 显示"设置已保存"成功提示
   - [ ] **不再出现 500 错误** ✅
   - [ ] 刷新页面后设置保持

7. **边界测试**
   - [ ] 设置免打扰时段为 00:00 - 23:59
   - [ ] 保存成功
   - [ ] 设置每日推荐为 1（最小值）
   - [ ] 保存成功
   - [ ] 设置每日推荐为 10（最大值）
   - [ ] 保存成功

## 数据库验证 🗄️

```sql
-- 查看用户偏好设置
SELECT * FROM user_content_preference 
WHERE user_id = '6e7ac151-100a-4427-a6ee-a5ac5b3c745e';
```

**验证点**：
- [ ] `content_recommendation_enabled` 为 boolean
- [ ] `preferred_sources` 为 JSONB 数组
- [ ] `excluded_topics` 为 JSONB 数组
- [ ] `max_daily_recommendations` 为 integer
- [ ] `quiet_hours_start` 为 time 类型（如 `22:00:00`）
- [ ] `quiet_hours_end` 为 time 类型（如 `08:00:00`）
- [ ] `updated_at` 自动更新

## 日志验证 📝

```bash
# 查看 API 日志
docker logs affinity-api --tail 50

# 查看 Celery Worker 日志
docker logs affinity-celery-worker --tail 50
```

**验证点**：
- [ ] 无 500 错误
- [ ] 无 `'str' object has no attribute 'hour'` 错误
- [ ] PUT /api/v1/content/preference 返回 200

## 自动化测试 🤖

```bash
cd backend
python test_content_preference_fix.py
```

**预期结果**: 所有测试通过 ✅

## 问题排查

如果仍然出现 500 错误：

1. **检查 API 日志**
   ```bash
   docker logs affinity-api --tail 100 | grep -A 5 "500\|error"
   ```

2. **检查数据库连接**
   ```bash
   docker exec -it affinity-postgres psql -U affinity -d affinity -c "\d user_content_preference"
   ```

3. **验证字段类型**
   ```sql
   SELECT column_name, data_type 
   FROM information_schema.columns 
   WHERE table_name = 'user_content_preference';
   ```

4. **检查前端请求**
   - 打开浏览器开发者工具 (F12)
   - Network 标签
   - 查看 PUT /api/v1/content/preference 请求
   - 检查 Request Payload 格式

## 修复状态

✅ **已完成** - 2026-01-20

- 后端时间字段转换逻辑已修复
- 前端字段映射已完成
- 自动化测试已通过
- 用户可以正常保存推荐设置
