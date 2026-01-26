@echo off
REM Run all evaluations sequentially
REM 顺序运行所有评测，避免冲突

echo ========================================
echo Running All Evaluations Sequentially
echo ========================================
echo.

REM Check backend
curl -s http://localhost:8000/health >nul 2>&1
if errorlevel 1 (
    echo ERROR: Backend is not running!
    exit /b 1
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
python affinity_evals/knowmebench/run_dataset1_pipeline.py --limit_samples 50
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
