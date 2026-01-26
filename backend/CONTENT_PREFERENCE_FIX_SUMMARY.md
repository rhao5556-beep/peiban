# 内容推荐偏好设置 500 错误修复总结

## 问题描述

用户在前端"推荐设置"页面点击"保存设置"按钮后，API 返回 500 错误。

## 根本原因

**时间字段类型不匹配**：
- PostgreSQL 数据库中 `quiet_hours_start` 和 `quiet_hours_end` 字段类型为 `time`
- 前端发送的是字符串格式 `"HH:MM"`（如 `"03:00"`）
- 后端代码直接将字符串传递给 SQLAlchemy，但 PostgreSQL 的 asyncpg 驱动期望 Python `time` 对象
- 错误信息：`'str' object has no attribute 'hour'`

## 修复方案

### 1. 时间字段转换逻辑（核心修复）

在 `backend/app/api/endpoints/content_recommendation.py` 的 `update_content_preference` 函数中添加类型检查和转换：

```python
from datetime import time as time_type

if preference.quiet_hours_start is not None:
    updates.append("quiet_hours_start = :start")
    if isinstance(preference.quiet_hours_start, str):
        try:
            hour, minute = map(int, preference.quiet_hours_start.split(':'))
            params["start"] = time_type(hour, minute)
        except (ValueError, AttributeError) as e:
            logger.error(f"Invalid quiet_hours_start format: {preference.quiet_hours_start}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid quiet_hours_start format. Expected HH:MM"
            )
    else:
        params["start"] = preference.quiet_hours_start
```

**关键改进**：
- ✅ 使用 `isinstance()` 检查类型
- ✅ 将字符串 `"HH:MM"` 转换为 `time(hour, minute)` 对象
- ✅ 添加详细的错误处理和日志
- ✅ 转换失败时返回 400 而不是 500

### 2. 前端字段映射（已在之前完成）

在 `frontend/src/services/api.ts` 中添加字段名映射：

```typescript
// 后端 → 前端
getContentPreference: async () => {
  const data = await response.json();
  return {
    enabled: !!data.content_recommendation_enabled,
    daily_limit: data.max_daily_recommendations ?? 1,
    preferred_sources: data.preferred_sources ?? [],
    quiet_hours_start: data.quiet_hours_start ?? null,
    quiet_hours_end: data.quiet_hours_end ?? null
  };
}

// 前端 → 后端
updateContentPreference: async (preferences: any) => {
  const payload = {
    content_recommendation_enabled: !!preferences.enabled,
    max_daily_recommendations: preferences.daily_limit ?? 1,
    preferred_sources: preferences.preferred_sources ?? [],
    quiet_hours_start: preferences.quiet_hours_start ?? undefined,
    quiet_hours_end: preferences.quiet_hours_end ?? undefined
  };
  // ...
}
```

## 测试验证

创建了完整的测试脚本 `test_content_preference_fix.py`，验证：

1. ✅ 启用推荐并设置所有字段
2. ✅ 只更新部分字段（其他字段保持不变）
3. ✅ 关闭推荐
4. ✅ 边界时间值（00:00 和 23:59）

所有测试通过，API 返回 200 状态码。

## 相关文件

- `backend/app/api/endpoints/content_recommendation.py` - 时间转换逻辑
- `frontend/src/services/api.ts` - 字段映射
- `backend/test_content_preference_fix.py` - 测试脚本

## 经验教训

1. **类型安全**：在 Python 中使用 SQLAlchemy 时，确保传递给数据库的参数类型与列类型匹配
2. **显式转换**：不要依赖隐式类型转换，特别是在异步数据库驱动中
3. **错误处理**：添加详细的错误日志和明确的 HTTP 状态码（400 vs 500）
4. **字段映射**：前后端字段名不一致时，在 API 层做统一映射

## 状态

✅ **已修复并验证** - 2026-01-20

前端用户现在可以正常保存推荐设置，所有字段（包括时间字段）都能正确保存到数据库。
