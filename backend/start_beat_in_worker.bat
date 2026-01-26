@echo off
echo 在 worker 容器中启动 Celery Beat（后台运行）...
docker exec -d affinity-celery-worker celery -A app.worker beat --loglevel=info
echo.
echo Celery Beat 已在后台启动！
echo 现在系统会每 30 秒自动处理新消息。
echo.
echo 验证 Beat 是否运行：
timeout /t 2 /nobreak >nul
docker exec affinity-celery-worker ps aux | findstr "celery.*beat"
echo.
pause
