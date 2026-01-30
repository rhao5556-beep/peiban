@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

echo ========================================
echo   Affinity Backend Eval Startup
echo ========================================

set EVAL_ENV=..\evals\.env.local
if exist %EVAL_ENV% (
  for /f "usebackq tokens=1,* delims==" %%A in ("%EVAL_ENV%") do (
    if not "%%A"=="" set "%%A=%%B"
  )
)

if not exist .env (
  if exist .env.example (
    copy .env.example .env >nul
  )
)

echo.
echo [1/3] Starting Docker services (postgres, redis, neo4j, milvus, celery)...
docker-compose up -d postgres redis neo4j etcd minio milvus celery-worker celery-beat
if %ERRORLEVEL% NEQ 0 (
  echo [错误] docker-compose up 失败，请确认 Docker Desktop 已启动
  exit /b 1
)

echo.
echo [2/3] Waiting for Milvus to be healthy...
timeout /t 5 /nobreak >nul

set RETRY=0
:check_milvus
curl -s http://localhost:9091/healthz >nul 2>&1
if errorlevel 1 (
  set /a RETRY+=1
  if !RETRY! GEQ 30 (
    echo [错误] Milvus 健康检查超时（http://localhost:9091/healthz）
    exit /b 1
  )
  timeout /t 2 /nobreak >nul
  goto check_milvus
)
echo Milvus: Ready

echo.
echo [3/3] Starting FastAPI server (local uvicorn)...
echo ========================================
echo   API Docs: http://localhost:8000/docs
echo   Health:   http://localhost:8000/health
echo ========================================
echo.
uvicorn app.main:app --reload --port 8000 --host 0.0.0.0

