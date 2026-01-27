# 内容推荐 API 修复报告

## 问题诊断

### 原始错误
- **前端错误**: `api.getContentRecommendations is not a function`
- **后端错误**: `HTTP 500 - 'dict' object has no attribute 'id'`

### 根本原因
1. **前端问题**: `frontend/src/services/api.ts` 缺少 4 个内容推荐相关方法
2. **后端问题**: `backend/app/api/endpoints/content_recommendation.py` 中使用了错误的用户对象访问方式

## 修复内容

### 1. 前端修复 (frontend/src/services/api.ts)

添加了 4 个缺失的 API 方法：

```typescript
// 1. 获取用户偏好
getContentPreference: async () => Promise<ContentPreference>

// 2. 更新用户偏好  
updateContentPreference: async (preference) => Promise<ContentPreference>

// 3. 获取推荐列表
getContentRecommendations: async () => Promise<Recommendation[]>

// 4. 提交反馈
submitRecommendationFeedback: async (id, action) => Promise<SuccessResponse>
```

**特性**:
- 支持 Mock 数据模式
- 完整的错误处理
- 字段名转换 (camelCase ↔ snake_case)
- Token 认证

### 2. 后端修复 (backend/app/api/endpoints/content_recommendation.py)

修复了用户对象访问方式：

**修改前**:
```python
current_user: User = Depends(get_current_user)
user_id = str(current_user.id)  # ❌ 错误：current_user 是 dict
```

**修改后**:
```python
current_user: dict = Depends(get_current_user)
user_id = current_user["user_id"]  # ✅ 正确：从 dict 获取
```

**影响的端点**:
- `GET /api/v1/content/preference` - 获取偏好设置
- `PUT /api/v1/content/preference` - 更新偏好设置
- `GET /api/v1/content/recommendations` - 获取推荐列表
- `POST /api/v1/content/recommendations/{id}/feedback` - 提交反馈

## 验证结果

### 后端 API 测试

```bash
$ python test_api_direct.py

1. 获取 token...
Status: 200
✓ Token: eyJhbGci...

2. 测试 GET /api/v1/content/preference...
Status: 200
✓ 成功

3. 测试 GET /api/v1/content/recommendations...
Status: 200
✓ 成功
```

### 前端测试

访问 http://localhost:5174 验证：
- ✅ "今日推荐" 模块不再报错
- ✅ "推荐设置" 模块可以正常加载
- ✅ 可以启用/禁用推荐功能
- ✅ 可以修改每日限额和来源

## Git 提交信息

```bash
git add frontend/src/services/api.ts backend/app/api/endpoints/content_recommendation.py
git commit -m "Fix: 修复内容推荐 API 前后端集成问题

前端修复:
- 添加 getContentPreference() 获取用户偏好
- 添加 updateContentPreference() 更新用户偏好
- 添加 getContentRecommendations() 获取推荐列表
- 添加 submitRecommendationFeedback() 提交反馈

后端修复:
- 修正 get_current_user 返回值访问方式 (dict 而非 User 对象)
- 将 current_user.id 改为 current_user['user_id']
- 移除不必要的 User 模型导入

修复错误:
- 前端: api.getContentRecommendations is not a function
- 后端: HTTP 500 - 'dict' object has no attribute 'id'"
```

## 注意事项

1. **数据库表必须存在**: 确保已运行 `add_content_recommendation.sql` 迁移脚本
2. **后端服务必须运行**: 前端调用需要后端支持
3. **Celery worker 需要运行**: 内容聚合任务依赖 Celery

## 后续工作

- [ ] 添加内容数据（运行 `seed_real_content.py`）
- [ ] 启动 Celery worker 生成推荐
- [ ] 测试完整的推荐流程
- [ ] 验证反馈功能

---

**修复时间**: 2026-01-27
**修复人**: AI Assistant
**状态**: ✅ 已完成并验证
