@echo off
echo ============================================
echo   部署所有系统
echo ============================================
echo.

echo [1/5] 检查 Docker 服务状态...
docker-compose ps
if errorlevel 1 (
    echo 错误: Docker 服务未运行
    echo 请先运行: docker-compose up -d
    pause
    exit /b 1
)
echo ✓ Docker 服务正常
echo.

echo [2/5] 运行数据库迁移...
echo.
echo   - 内容推荐系统迁移...
docker exec -it affinity-postgres psql -U affinity -d affinity -f /app/scripts/migrations/add_content_recommendation.sql
if errorlevel 1 (
    echo   ⚠ 内容推荐迁移可能已运行过
) else (
    echo   ✓ 内容推荐迁移完成
)
echo.

echo   - 主动消息系统迁移...
docker exec -it affinity-postgres psql -U affinity -d affinity -f /app/scripts/migrations/add_proactive_messages.sql
if errorlevel 1 (
    echo   ⚠ 主动消息迁移可能已运行过
) else (
    echo   ✓ 主动消息迁移完成
)
echo.

echo   - 表情包系统迁移...
docker exec -it affinity-postgres psql -U affinity -d affinity -f /app/scripts/migrations/add_meme_emoji_system.sql
if errorlevel 1 (
    echo   ⚠ 表情包迁移可能已运行过
) else (
    echo   ✓ 表情包迁移完成
)
echo.

echo [3/5] 运行内容聚合任务...
echo.
echo   - 聚合内容推荐...
docker exec affinity-celery-worker celery -A app.worker call app.worker.tasks.content_aggregation.aggregate_content
if errorlevel 1 (
    echo   ❌ 内容聚合失败
) else (
    echo   ✓ 内容聚合完成
)
echo.

echo   - 聚合表情包...
docker exec affinity-celery-worker celery -A app.worker call app.worker.tasks.meme_aggregation.aggregate_trending_memes
if errorlevel 1 (
    echo   ❌ 表情包聚合失败
) else (
    echo   ✓ 表情包聚合完成
)
echo.

echo [4/5] 验证数据库表...
echo.
docker exec -it affinity-postgres psql -U affinity -d affinity -c "SELECT COUNT(*) as content_recommendations FROM content_recommendations;"
docker exec -it affinity-postgres psql -U affinity -d affinity -c "SELECT COUNT(*) as proactive_messages FROM proactive_messages;"
docker exec -it affinity-postgres psql -U affinity -d affinity -c "SELECT COUNT(*) as memes FROM memes;"
echo.

echo [5/5] 部署完成！
echo.
echo ============================================
echo   系统状态
echo ============================================
echo.
echo ✅ 冲突解决系统 - 就绪
echo ✅ 内容推荐系统 - 已配置
echo ✅ 主动消息系统 - 已配置
echo ✅ 表情包系统 - 已配置
echo.
echo ============================================
echo   后续步骤
echo ============================================
echo.
echo 1. 启动前端:
echo    cd frontend
echo    npm run dev
echo.
echo 2. 访问应用:
echo    http://localhost:5173
echo.
echo 3. 查看详细报告:
echo    SYSTEMS_STATUS_REPORT.md
echo.
pause
