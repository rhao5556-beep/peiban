@echo off
REM Quick LoCoMo Test - 快速测试 LoCoMo 评测流程
REM 只测试 1 个对话，5 个问题

echo ========================================
echo LoCoMo Quick Test
echo ========================================
echo.
echo This will run a quick test with:
echo - 1 conversation
echo - 5 questions per conversation
echo - LLM-based scoring
echo.

REM Check backend
curl -s http://localhost:8000/health >nul 2>&1
if errorlevel 1 (
    echo ERROR: Backend is not running!
    echo Please start: cd backend ^&^& start-dev.bat
    exit /b 1
)

echo Backend is running ✓
echo.
echo Starting quick test...
echo.

REM Run quick test
call evals\run_full_locomo_pipeline.bat --limit_conversations 1 --limit_questions 5

echo.
echo ========================================
echo Quick Test Complete!
echo ========================================
echo.
echo Check the outputs/locomo_run/ directory for results.
echo.

exit /b 0
