@echo off
REM KnowMeBench 快速评测脚本
REM 使用方法：
REM   run_knowmebench_eval.bat quick    - 快速测试（每个任务 3 题）
REM   run_knowmebench_eval.bat full     - 完整评测（所有题目）
REM   run_knowmebench_eval.bat judge    - 对最新结果运行 Judge 评分

setlocal enabledelayedexpansion

set BACKEND_URL=http://localhost:8000
set MODE=graph_only
set CONCURRENCY=4

REM 检查参数
if "%1"=="" (
    echo 使用方法：
    echo   run_knowmebench_eval.bat quick    - 快速测试（每个任务 3 题）
    echo   run_knowmebench_eval.bat full     - 完整评测（所有题目）
    echo   run_knowmebench_eval.bat judge    - 对最新结果运行 Judge 评分
    exit /b 1
)

REM 检查后端服务
echo [1/3] 检查后端服务...
curl -s %BACKEND_URL%/api/v1/health >nul 2>&1
if errorlevel 1 (
    echo [错误] 后端服务未运行！
    echo 请先启动后端服务：
    echo   cd backend
    echo   docker-compose up -d
    echo   uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
    exit /b 1
)
echo [✓] 后端服务正常

if "%1"=="judge" goto run_judge

REM 运行评测
echo.
echo [2/3] 运行 KnowMeBench 评测...
echo 模式: %MODE%
echo 并发: %CONCURRENCY%

if "%1"=="quick" (
    echo 类型: 快速测试（每个任务 3 题）
    python evals/run_knowmebench_dataset1_pipeline.py --backend_base_url %BACKEND_URL% --mode %MODE% --eval_mode --limit_per_task 3 --concurrency %CONCURRENCY%
) else if "%1"=="full" (
    echo 类型: 完整评测（所有题目）
    python evals/run_knowmebench_dataset1_pipeline.py --backend_base_url %BACKEND_URL% --mode %MODE% --eval_mode --concurrency %CONCURRENCY%
) else (
    echo [错误] 未知参数: %1
    exit /b 1
)

if errorlevel 1 (
    echo [错误] 评测运行失败！
    exit /b 1
)

echo.
echo [✓] 评测完成！
echo.
echo 输出目录已打印在上方，请复制用于下一步 Judge 评分
echo.
echo 运行 Judge 评分：
echo   run_knowmebench_eval.bat judge
exit /b 0

:run_judge
echo.
echo [2/3] 查找最新评测结果...

REM 查找最新的输出目录
for /f "delims=" %%i in ('dir /b /ad /o-d outputs\knowmebench_run\ds1_pipeline_* 2^>nul') do (
    set LATEST_DIR=outputs\knowmebench_run\%%i
    goto found_dir
)

echo [错误] 未找到评测结果目录！
echo 请先运行评测：
echo   run_knowmebench_eval.bat quick
echo   或
echo   run_knowmebench_eval.bat full
exit /b 1

:found_dir
echo [✓] 找到最新结果: %LATEST_DIR%

echo.
echo [3/3] 运行 Judge 评分...
python evals/run_knowmebench_official_judge.py --input_dir %LATEST_DIR% --output_file %LATEST_DIR%\judge_results.json --judge_model Pro/deepseek-ai/DeepSeek-V3.2 --concurrency 4

if errorlevel 1 (
    echo [错误] Judge 评分失败！
    exit /b 1
)

echo.
echo [✓] Judge 评分完成！
echo.
echo 结果文件: %LATEST_DIR%\judge_results.json
echo.
echo 查看结果：
echo   type %LATEST_DIR%\judge_results.json
exit /b 0
