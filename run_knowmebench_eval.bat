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

if "%1"=="judge" goto run_judge

echo [1/3] 环境预检...
python evals/check_eval_env.py --backend_base_url %BACKEND_URL% --timeout_s 10 --skip_judge_probe
if errorlevel 1 (
    exit /b %errorlevel%
)

REM 运行评测
echo.
echo [2/3] 运行 KnowMeBench 评测...
echo 模式: %MODE%
echo 并发: %CONCURRENCY%

if "%1"=="quick" (
    echo 类型: 快速测试（每个任务 3 题）
    if exist affinity_evals\knowmebench\run_dataset1_pipeline.py (
        python affinity_evals/knowmebench/run_dataset1_pipeline.py --backend_base_url %BACKEND_URL% --mode %MODE% --eval_mode --limit_per_task 3 --concurrency %CONCURRENCY%
    ) else (
        set KM_PIPE=
        for /f "delims=" %%i in ('dir /b affinity_evals\knowmebench\__pycache__\run_dataset1_pipeline.*.pyc 2^>nul') do (
            set KM_PIPE=affinity_evals\knowmebench\__pycache__\%%i
            goto km_quick_found
        )
        :km_quick_found
        if not defined KM_PIPE (
            echo [错误] 未找到 KnowMeBench 评测入口！
            exit /b 1
        )
        python %KM_PIPE% --backend_base_url %BACKEND_URL% --mode %MODE% --eval_mode --limit_per_task 3 --concurrency %CONCURRENCY%
    )
) else if "%1"=="full" (
    echo 类型: 完整评测（所有题目）
    if exist affinity_evals\knowmebench\run_dataset1_pipeline.py (
        python affinity_evals/knowmebench/run_dataset1_pipeline.py --backend_base_url %BACKEND_URL% --mode %MODE% --eval_mode --concurrency %CONCURRENCY%
    ) else (
        set KM_PIPE=
        for /f "delims=" %%i in ('dir /b affinity_evals\knowmebench\__pycache__\run_dataset1_pipeline.*.pyc 2^>nul') do (
            set KM_PIPE=affinity_evals\knowmebench\__pycache__\%%i
            goto km_full_found
        )
        :km_full_found
        if not defined KM_PIPE (
            echo [错误] 未找到 KnowMeBench 评测入口！
            exit /b 1
        )
        python %KM_PIPE% --backend_base_url %BACKEND_URL% --mode %MODE% --eval_mode --concurrency %CONCURRENCY%
    )
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
echo [1/3] 环境预检...
python evals/check_eval_env.py --backend_base_url %BACKEND_URL% --timeout_s 10 --require_judge
if errorlevel 1 (
    exit /b %errorlevel%
)

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
if exist affinity_evals\knowmebench\official_judge.py (
    python affinity_evals/knowmebench/official_judge.py --input_dir %LATEST_DIR% --output_file %LATEST_DIR%\judge_results.json --concurrency 4
) else (
    set KM_JUDGE=
    for /f "delims=" %%i in ('dir /b affinity_evals\knowmebench\__pycache__\official_judge.*.pyc 2^>nul') do (
        set KM_JUDGE=affinity_evals\knowmebench\__pycache__\%%i
        goto km_judge_found
    )
    :km_judge_found
    if not defined KM_JUDGE (
        echo [错误] 未找到 Judge 入口！
        exit /b 1
    )
    python %KM_JUDGE% --input_dir %LATEST_DIR% --output_file %LATEST_DIR%\judge_results.json --concurrency 4
)

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
