@echo off
chcp 65001 >nul
REM Affinity Backend Development Startup Script
REM 启动后端开发环境（端口 8000）

echo ========================================
echo   Affinity Backend Dev Startup
echo ========================================

REM 0. 检查 .env 文件
echo.
echo [0/4] Checking .env file...
if not exist .env (
    echo     警告: 根目录缺失 .env 文件
    if exist .env.example (
        echo     自动复制 .env.example 为 .env...
        copy .env.example .env >nul
        echo     已创建 .env，请根据需要编辑配置
    ) else (
        echo     错误: 找不到 .env.example，请手动创建 .env
        pause
        exit /b 1
    )
) else (
    echo     .env: OK
)

REM 1. 启动 Docker 服务（postgres, redis, neo4j）
echo.
echo [1/4] Starting Docker services...
docker-compose up -d postgres redis neo4j
if %ERRORLEVEL% NEQ 0 (
    echo     错误: docker-compose up 失败
    echo     请确保 Docker Desktop 已启动
    pause
    exit /b 1
)

REM 2. 等待容器就绪
echo.
echo [2/4] Waiting for containers to be healthy...
timeout /t 8 /nobreak > nul

REM 检查 PostgreSQL
:check_postgres
docker exec affinity-postgres pg_isready -U affinity > nul 2>&1
if errorlevel 1 (
    echo     Waiting for PostgreSQL...
    timeout /t 2 /nobreak > nul
    goto check_postgres
)
echo     PostgreSQL: Ready

REM 检查 Redis
docker exec affinity-redis redis-cli ping > nul 2>&1
if errorlevel 1 (
    echo     Redis: Not ready, continuing anyway...
) else (
    echo     Redis: Ready
)

REM 检查 Neo4j
curl -s http://localhost:7474 > nul 2>&1
if errorlevel 1 (
    echo     Neo4j: Not ready, continuing anyway...
) else (
    echo     Neo4j: Ready
)

REM 3. 检查 Python 依赖
echo.
echo [3/4] Checking Python environment...
python --version >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo     错误: Python 未安装或不在 PATH 中
    pause
    exit /b 1
)
echo     Python: OK

REM 4. 启动 FastAPI 服务
echo.
echo [4/4] Starting FastAPI server on port 8000...
echo.
echo ========================================
echo   API Docs: http://localhost:8000/docs
echo   Health:   http://localhost:8000/health
echo   前端连接: http://localhost:5173 (如果前端在本机)
echo ========================================
echo.
echo   按 Ctrl+C 停止服务
echo.

uvicorn app.main:app --reload --port 8000 --host 0.0.0.0
