#!/bin/bash
# Celery Beat 容器启动脚本 - 安装缺失的依赖后启动服务

set -e

echo "Installing missing dependencies..."
pip install --no-cache-dir feedparser==6.0.11 circuitbreaker==2.0.0

echo "Starting Celery beat..."
exec celery -A app.worker beat --loglevel=info
