@echo off
REM LoCoMo Complete Evaluation Pipeline
REM 使用真实 LLM 进行陪伴系统评测

echo ========================================
echo LoCoMo Evaluation Pipeline
echo ========================================
echo.

REM Check if backend is running
echo [1/4] Checking backend status...
curl -s http://localhost:8000/health >nul 2>&1
if errorlevel 1 (
    echo ERROR: Backend is not running!
    echo Please start backend first: cd backend ^&^& start-dev.bat
    exit /b 1
)
echo Backend is running ✓
echo.

REM Set default parameters
set BACKEND_URL=http://localhost:8000
set MODE=hybrid
set LIMIT_CONVERSATIONS=0
set LIMIT_QUESTIONS=0

REM Parse command line arguments
:parse_args
if "%1"=="" goto run_eval
if "%1"=="--mode" (
    set MODE=%2
    shift
    shift
    goto parse_args
)
if "%1"=="--limit_conversations" (
    set LIMIT_CONVERSATIONS=%2
    shift
    shift
    goto parse_args
)
if "%1"=="--limit_questions" (
    set LIMIT_QUESTIONS=%2
    shift
    shift
    goto parse_args
)
shift
goto parse_args

:run_eval
echo Configuration:
echo - Backend URL: %BACKEND_URL%
echo - Mode: %MODE%
if not "%LIMIT_CONVERSATIONS%"=="0" echo - Limit conversations: %LIMIT_CONVERSATIONS%
if not "%LIMIT_QUESTIONS%"=="0" echo - Limit questions: %LIMIT_QUESTIONS%
echo.

REM Run evaluation
echo [2/4] Running LoCoMo evaluation...
python evals/run_locomo10_pipeline.py ^
    --backend_base_url %BACKEND_URL% ^
    --dataset_path data/locomo/locomo10.json ^
    --output_dir outputs/locomo_run ^
    --mode %MODE% ^
    --eval_mode ^
    --limit_conversations %LIMIT_CONVERSATIONS% ^
    --limit_questions %LIMIT_QUESTIONS% ^
    --chunk_size 64 ^
    --sleep_after_memorize_s 0.5

if errorlevel 1 (
    echo ERROR: Evaluation failed!
    exit /b 1
)
echo Evaluation completed ✓
echo.

REM Find the latest output directory
for /f "delims=" %%i in ('dir /b /ad /o-d outputs\locomo_run\locomo10_%MODE%_*') do (
    set LATEST_DIR=outputs\locomo_run\%%i
    goto found_dir
)
:found_dir

if not defined LATEST_DIR (
    echo ERROR: Could not find output directory!
    exit /b 1
)

echo Latest output: %LATEST_DIR%
echo.

REM Find the model outputs file
for /f "delims=" %%i in ('dir /b /o-d "%LATEST_DIR%\*.model_outputs.json"') do (
    set MODEL_OUTPUTS=%LATEST_DIR%\%%i
    goto found_outputs
)
:found_outputs

if not defined MODEL_OUTPUTS (
    echo ERROR: Could not find model outputs file!
    exit /b 1
)

echo Model outputs: %MODEL_OUTPUTS%
echo.

REM Score with LLM judge
echo [3/4] Scoring with LLM judge...
python evals/score_locomo_with_llm.py ^
    --in_path "%MODEL_OUTPUTS%" ^
    --out_path "%LATEST_DIR%\scoring_summary.json" ^
    --failures_out_path "%LATEST_DIR%\failures.json" ^
    --detailed_out_path "%LATEST_DIR%\detailed_scores.json" ^
    --use_llm ^
    --rate_limit_delay 0.1

if errorlevel 1 (
    echo ERROR: Scoring failed!
    exit /b 1
)
echo Scoring completed ✓
echo.

REM Generate report
echo [4/4] Generating evaluation report...
python evals/generate_locomo_report.py ^
    --summary_path "%LATEST_DIR%\scoring_summary.json" ^
    --failures_path "%LATEST_DIR%\failures.json" ^
    --output_path "%LATEST_DIR%\EVALUATION_REPORT.md"

if errorlevel 1 (
    echo Warning: Report generation failed, but evaluation is complete
)

echo.
echo ========================================
echo Evaluation Complete!
echo ========================================
echo.
echo Results saved to: %LATEST_DIR%
echo - scoring_summary.json: Overall metrics
echo - failures.json: Failed cases
echo - detailed_scores.json: All scores with reasoning
echo - EVALUATION_REPORT.md: Human-readable report
echo.
echo To view results:
echo   type "%LATEST_DIR%\EVALUATION_REPORT.md"
echo.

exit /b 0
