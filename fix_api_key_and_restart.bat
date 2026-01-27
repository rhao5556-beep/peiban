@echo off
echo ========================================
echo 修复 API Key 配置并重启 Celery Worker
echo ========================================
echo.

echo [1/5] 检查当前 API Key 配置...
echo.
echo backend/.env 文件:
type backend\.env | findstr OPENAI
echo.
echo Celery worker 容器环境变量:
docker exec affinity-celery-worker printenv | findstr OPENAI
echo.

echo [2/5] 停止 Celery worker 和 beat...
docker stop affinity-celery-worker
docker stop affinity-celery-beat
echo.

echo [3/5] 重新启动服务（加载新的环境变量）...
cd backend
docker-compose up -d celery-worker celery-beat
cd ..
echo.

echo [4/5] 等待服务启动（10秒）...
timeout /t 10 /nobreak
echo.

echo [5/5] 验证新的环境变量...
echo.
echo Celery worker 容器环境变量（更新后）:
docker exec affinity-celery-worker printenv | findstr OPENAI
echo.

echo ========================================
echo 修复完成！
echo ========================================
echo.
echo 下一步：
echo 1. 查看 worker 日志，确认不再有 401 错误
echo    docker logs affinity-celery-worker --tail 50 -f
echo.
echo 2. 监控 Outbox 处理进度
echo    python backend\check_outbox_status.py
echo.
echo 3. 等待积压事件处理完成（可能需要数小时）
echo.
pause
