@echo off
REM Run all evaluations sequentially
REM 顺序运行所有评测，避免冲突

echo ========================================
echo Running All Evaluations Sequentially
echo ========================================
echo.

python evals/check_eval_env.py --backend_base_url http://localhost:8000 --timeout_s 10 --skip_judge_probe
if errorlevel 1 (
    exit /b %errorlevel%
)

echo [1/3] Running LoCoMo Evaluation...
echo.
python evals/run_full_locomo_pipeline.py --limit_conversations 2 --limit_questions 10
if errorlevel 1 (
    echo ERROR: LoCoMo evaluation failed!
    exit /b 1
)

echo.
echo ========================================
echo LoCoMo Complete! Waiting 10 seconds...
echo ========================================
timeout /t 10 /nobreak

echo.
echo [2/3] Running KnowMeBench Evaluation...
echo.
if exist affinity_evals\knowmebench\run_dataset1_pipeline.py (
    python affinity_evals/knowmebench/run_dataset1_pipeline.py --limit_samples 50
) else (
    set KM_PIPE=
    for /f "delims=" %%i in ('dir /b affinity_evals\knowmebench\__pycache__\run_dataset1_pipeline.*.pyc 2^>nul') do (
        set KM_PIPE=affinity_evals\knowmebench\__pycache__\%%i
        goto km_found
    )
    :km_found
    if not defined KM_PIPE (
        echo ERROR: KnowMeBench pipeline entry not found!
        exit /b 1
    )
    python %KM_PIPE% --limit_samples 50
)
if errorlevel 1 (
    echo ERROR: KnowMeBench evaluation failed!
    exit /b 1
)

echo.
echo ========================================
echo KnowMeBench Complete! Waiting 10 seconds...
echo ========================================
timeout /t 10 /nobreak

echo.
echo [3/3] Running Custom Quality Tests...
echo.
python backend/test_conversation_quality.py
if errorlevel 1 (
    echo Warning: Quality tests had issues
)

echo.
echo ========================================
echo All Evaluations Complete!
echo ========================================
echo.
echo Check results in:
echo - outputs/locomo_run/
echo - outputs/knowmebench_run/
echo.

exit /b 0
