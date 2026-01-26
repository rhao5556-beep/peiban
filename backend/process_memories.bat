@echo off
echo 正在处理待处理的记忆...
docker exec affinity-celery-worker celery -A app.worker call app.worker.tasks.outbox.process_pending_events
echo 完成！等待 10 秒查看结果...
timeout /t 10 /nobreak
docker exec affinity-postgres psql -U affinity -d affinity -c "SELECT COUNT(*) as pending_count FROM memories WHERE status = 'pending';"
echo.
echo 如果 pending_count 为 0，说明所有记忆都已处理完成！
pause
