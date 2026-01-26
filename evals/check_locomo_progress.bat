@echo off
REM Check LoCoMo Evaluation Progress
REM 检查 LoCoMo 评测进度

echo ========================================
echo LoCoMo Evaluation Progress Checker
echo ========================================
echo.

REM Find latest directory
for /f "delims=" %%i in ('dir /b /ad /o-d outputs\locomo_run 2^>nul') do (
    set LATEST_DIR=outputs\locomo_run\%%i
    goto found_dir
)

echo No evaluation directories found!
exit /b 1

:found_dir
echo Latest evaluation directory:
echo %LATEST_DIR%
echo.

REM Check if files exist
if exist "%LATEST_DIR%\*.model_outputs.json" (
    echo [1/3] Evaluation Phase: COMPLETED ✓
    
    REM Count questions
    for /f %%a in ('powershell -Command "(Get-Content '%LATEST_DIR%\*.model_outputs.json' | ConvertFrom-Json).Count"') do set QUESTION_COUNT=%%a
    echo       Questions answered: %QUESTION_COUNT%
) else (
    echo [1/3] Evaluation Phase: RUNNING...
    echo       Injecting conversations and asking questions
)

echo.

if exist "%LATEST_DIR%\scoring_summary*.json" (
    echo [2/3] Scoring Phase: COMPLETED ✓
    
    REM Show accuracy
    for /f %%a in ('powershell -Command "$json = Get-Content '%LATEST_DIR%\scoring_summary*.json' | ConvertFrom-Json; [math]::Round($json.accuracy * 100, 1)"') do set ACCURACY=%%a
    echo       Accuracy: %ACCURACY%%%
) else (
    echo [2/3] Scoring Phase: WAITING or RUNNING...
    echo       Will start after evaluation completes
)

echo.

if exist "%LATEST_DIR%\EVALUATION_REPORT.md" (
    echo [3/3] Report Generation: COMPLETED ✓
    echo.
    echo ========================================
    echo Evaluation Complete!
    echo ========================================
    echo.
    echo View report:
    echo   type "%LATEST_DIR%\EVALUATION_REPORT.md"
) else (
    echo [3/3] Report Generation: WAITING...
    echo       Will start after scoring completes
)

echo.
echo ========================================
echo.
echo To refresh, run this script again:
echo   evals\check_locomo_progress.bat
echo.

exit /b 0
