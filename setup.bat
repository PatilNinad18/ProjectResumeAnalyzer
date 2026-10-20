@echo off
setlocal enabledelayedexpansion

title ProjectResumeAnalyzer - First Time Setup

echo =====================================================================
echo   ProjectResumeAnalyzer - Windows Setup
echo =====================================================================
echo.

set "ROOT_DIR=%~dp0"
cd /d "%ROOT_DIR%"

:: -----------------------------------------------------------------------
:: Step 1: Check System Prerequisites
:: -----------------------------------------------------------------------
echo [1/4] Checking system prerequisites...

:: Check Python
python --version >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Python is not installed or not found in PATH.
    echo         Please install Python 3.10 or higher from https://www.python.org/
    echo         Make sure to check "Add Python to PATH" during installation.
    goto :error
)
for /f "tokens=*" %%i in ('python --version 2^>^&1') do set "PY_VER=%%i"
echo   [OK] Found %PY_VER%

:: Check Node.js
node --version >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Node.js is not installed or not found in PATH.
    echo         Please install Node.js 18 or higher from https://nodejs.org/
    goto :error
)
for /f "tokens=*" %%i in ('node --version 2^>^&1') do set "NODE_VER=%%i"
echo   [OK] Found Node.js %NODE_VER%

:: Check npm
call npm --version >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [ERROR] npm is not found in PATH.
    goto :error
)
for /f "tokens=*" %%i in ('call npm --version 2^>^&1') do set "NPM_VER=%%i"
echo   [OK] Found npm %NPM_VER%

:: Check Ollama - informational only, not required for baseline extraction
ollama --version >nul 2>&1
if %ERRORLEVEL% equ 0 (
    for /f "tokens=*" %%i in ('ollama --version 2^>^&1') do set "OLLAMA_VER=%%i"
    echo   [OK] Found %OLLAMA_VER%
) else (
    echo   [INFO] Ollama not found in PATH.
    echo          Note: Ollama is optional for basic analysis, but needed
    echo          for local AI evidence enrichment and interactive chat.
    echo          Download if desired from https://ollama.com/
)
echo.

:: -----------------------------------------------------------------------
:: Step 2: Configure Environment (.env)
:: -----------------------------------------------------------------------
echo [2/4] Setting up environment configuration...

if not exist "%ROOT_DIR%backend\.env" (
    if exist "%ROOT_DIR%backend\.env.example" (
        copy "%ROOT_DIR%backend\.env.example" "%ROOT_DIR%backend\.env" >nul
        echo   [OK] Created backend\.env from backend\.env.example with offline defaults.
    ) else (
        echo   [WARN] backend\.env.example not found. Creating minimal backend\.env...
        (
            echo DATABASE_URL=sqlite:///./jd_agent.db
            echo STORAGE_BACKEND=local
            echo LOCAL_STORAGE_PATH=./storage_data
            echo QUEUE_BACKEND=local
            echo LLM_PROVIDER=ollama
            echo LLM_MODEL=qwen3:4b
            echo OLLAMA_BASE_URL=http://localhost:11434
        ) > "%ROOT_DIR%backend\.env"
        echo   [OK] Created minimal backend\.env.
    )
) else (
    echo   [OK] Found existing backend\.env - preserving your existing settings.
)
echo.

:: -----------------------------------------------------------------------
:: Step 3: Setup Backend Python Virtual Environment
:: -----------------------------------------------------------------------
echo [3/4] Setting up Python virtual environment and dependencies...

if not exist "%ROOT_DIR%backend\.venv\Scripts\python.exe" (
    echo   Creating Python virtual environment in backend\.venv...
    python -m venv "%ROOT_DIR%backend\.venv"
    if !ERRORLEVEL! neq 0 (
        echo [ERROR] Failed to create virtual environment.
        goto :error
    )
    echo   [OK] Virtual environment created.
) else (
    echo   [OK] Virtual environment already exists at backend\.venv.
)

echo   Installing backend dependencies from backend\requirements.txt...
"%ROOT_DIR%backend\.venv\Scripts\python.exe" -m pip install --upgrade pip >nul 2>&1
"%ROOT_DIR%backend\.venv\Scripts\python.exe" -m pip install -r "%ROOT_DIR%backend\requirements.txt"
if !ERRORLEVEL! neq 0 (
    echo [ERROR] Failed to install backend dependencies.
    goto :error
)
echo   [OK] Backend dependencies installed successfully.

echo   Initializing SQLite database...
cd /d "%ROOT_DIR%backend"
"%ROOT_DIR%backend\.venv\Scripts\python.exe" -c "from app.db import init_db; init_db()" >nul 2>&1
if !ERRORLEVEL! neq 0 (
    echo   [WARN] Database auto-initialization returned non-zero; it will initialize on first app start.
) else (
    echo   [OK] Database initialized at backend\jd_agent.db.
)
cd /d "%ROOT_DIR%"
echo.

:: -----------------------------------------------------------------------
:: Step 4: Setup Frontend Node Dependencies
:: -----------------------------------------------------------------------
echo [4/4] Setting up frontend dependencies...

cd /d "%ROOT_DIR%frontend"
if not exist "%ROOT_DIR%frontend\node_modules" (
    echo   Installing frontend npm packages - this may take a minute...
    call npm install
    if !ERRORLEVEL! neq 0 (
        echo [ERROR] npm install failed in frontend.
        goto :error
    )
    echo   [OK] Frontend dependencies installed.
) else (
    echo   [OK] Frontend node_modules already exists. Verifying packages...
    call npm install
    echo   [OK] Frontend dependencies verified.
)
cd /d "%ROOT_DIR%"
echo.

:: -----------------------------------------------------------------------
:: Setup Complete
:: -----------------------------------------------------------------------
echo =====================================================================
echo   Setup Completed Successfully!
echo =====================================================================
echo.
echo   You are now ready to launch ProjectResumeAnalyzer:
echo.
echo     1. To start the application (Backend and Frontend):
echo        run.bat
echo.
echo     2. To stop all running services safely:
echo        stop.bat
echo.
echo     3. Optional: For AI Evidence Enrichment and JD Chat:
echo        - Start Ollama:  ollama serve
echo        - Pull model:    ollama pull qwen3:4b
echo        Note: Deterministic analysis works completely offline without Ollama.
echo.
echo =====================================================================
goto :end

:error
echo.
echo =====================================================================
echo   Setup encountered an error. Please see the messages above.
echo =====================================================================
exit /b 1

:end
exit /b 0
