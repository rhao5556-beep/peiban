@echo off
REM 临时解决方案：在容器启动时安装缺失的依赖

echo 正在启动 Celery Worker 和 Beat（带依赖安装）...

REM 停止现有容器
docker-compose stop celery-worker celery-beat

REM 启动 celery-worker 容器（不立即执行命令）
docker-compose up -d celery-worker

REM 等待容器启动
timeout /t 3 /nobreak > nul

REM 在容器内安装 feedparser
echo 安装 feedparser 依赖...
docker exec affinity-celery-worker pip install feedparser==6.0.11 circuitbreaker==2.0.0

REM 重启容器以应用更改
echo 重启 Celery 服务...
docker-compose restart celery-worker

REM 启动 celery-beat
docker-compose up -d celery-beat

REM 等待启动
timeout /t 3 /nobreak > nul

REM 检查状态
echo.
echo ========================================
echo Celery 服务状态：
docker ps --filter "name=celery"

echo.
echo ========================================
echo Celery Worker 日志（最后10行）：
docker logs affinity-celery-worker --tail 10

echo.
echo ========================================
echo Celery Beat 日志（最后10行）：
docker logs affinity-celery-beat --tail 10

echo.
echo ========================================
echo 完成！
echo.
echo 手动触发内容抓取测试：
echo docker exec affinity-celery-worker celery -A app.worker call app.worker.tasks.content_aggregation.test_fetch_content
echo.
echo 查看 Celery 任务列表：
echo docker exec affinity-celery-worker celery -A app.worker inspect registered
