@echo off
chcp 65001 >nul
setlocal

echo ========================================
echo   Affinity Eval Stack Check
echo ========================================

echo.
echo [1/4] Docker containers:
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" | findstr /i "affinity-"

echo.
echo [2/4] Milvus health:
curl -s http://localhost:9091/healthz
echo.

echo.
echo [3/4] Postgres ready:
docker exec affinity-postgres pg_isready -U affinity

echo.
echo [4/4] Outbox pending count (postgres):
docker exec affinity-postgres psql -U affinity -d affinity -c "select status, count(*) from outbox_events group by status order by status;"

