@echo off
REM LoCoMo Complete Evaluation Pipeline
REM 使用真实 LLM 进行陪伴系统评测

set BACKEND_URL=http://localhost:8000
set MODE=hybrid
set LIMIT_CONVERSATIONS=0
set LIMIT_QUESTIONS=0
set NO_LLM=
set SKIP_ENV_CHECK=

echo ========================================
echo LoCoMo Evaluation Pipeline
echo ========================================
echo.

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
if "%1"=="--no_llm" (
    set NO_LLM=--no_llm
    shift
    goto parse_args
)
if "%1"=="--skip_env_check" (
    set SKIP_ENV_CHECK=--skip_env_check
    shift
    goto parse_args
)
shift
goto parse_args

:run_eval
python evals/check_eval_env.py --backend_base_url %BACKEND_URL% --timeout_s 10 --skip_judge_probe
if errorlevel 1 (
    exit /b %errorlevel%
)

echo Configuration:
echo - Backend URL: %BACKEND_URL%
echo - Mode: %MODE%
if not "%LIMIT_CONVERSATIONS%"=="0" echo - Limit conversations: %LIMIT_CONVERSATIONS%
if not "%LIMIT_QUESTIONS%"=="0" echo - Limit questions: %LIMIT_QUESTIONS%
echo.

python evals/run_full_locomo_pipeline.py --backend_url %BACKEND_URL% --mode %MODE% --limit_conversations %LIMIT_CONVERSATIONS% --limit_questions %LIMIT_QUESTIONS% %NO_LLM% %SKIP_ENV_CHECK%
exit /b %errorlevel%
