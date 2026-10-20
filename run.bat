@echo off
setlocal enabledelayedexpansion

title ProjectResumeAnalyzer - Launcher

set "ROOT_DIR=%~dp0"
cd /d "%ROOT_DIR%"

echo =====================================================================
echo   Starting ProjectResumeAnalyzer
echo =====================================================================
echo.

:: -----------------------------------------------------------------------
:: Prerequisite Checks
:: -----------------------------------------------------------------------
if not exist "%ROOT_DIR%backend\.venv\Scripts\python.exe" (
    echo [ERROR] Python virtual environment was not found at:
    echo         backend\.venv
    echo.
    echo         Please run first-time setup first:
    echo           setup.bat
    echo.
    pause
    exit /b 1
)

if not exist "%ROOT_DIR%backend\.env" (
    if exist "%ROOT_DIR%backend\.env.example" (
        echo [WARN] backend\.env not found. Creating from backend\.env.example...
        copy "%ROOT_DIR%backend\.env.example" "%ROOT_DIR%backend\.env" >nul
        echo   [OK] backend\.env created with default offline settings.
    )
)

if not exist "%ROOT_DIR%frontend\node_modules" (
    echo [ERROR] Frontend dependencies were not found at:
    echo         frontend\node_modules
    echo.
    echo         Please run first-time setup first:
    echo           setup.bat
    echo.
    pause
    exit /b 1
)

:: -----------------------------------------------------------------------
:: Check Ollama Status (Informational)
:: -----------------------------------------------------------------------
powershell -NoProfile -Command "try { $r = Invoke-WebRequest -Uri 'http://localhost:11434/api/tags' -TimeoutSec 2 -UseBasicParsing; exit 0 } catch { exit 1 }" >nul 2>&1
if %ERRORLEVEL% equ 0 (
    echo [OK] Ollama service detected and running on http://localhost:11434.
) else (
    echo [INFO] Ollama service is not currently running on port 11434.
    echo        - Note: Deterministic JD analysis works 100%% offline without Ollama.
    echo        - For AI evidence enrichment and chat, start Ollama in another terminal:
    echo            ollama serve
)
echo.

:: -----------------------------------------------------------------------
:: Port Conflict Checks
:: -----------------------------------------------------------------------
netstat -ano | findstr /R /C:":8000 .*LISTENING" >nul 2>&1
if %ERRORLEVEL% equ 0 (
    echo [WARN] Port 8000 is already in use.
    echo        A backend instance may already be running, or another process is on port 8000.
)

netstat -ano | findstr /R /C:":3000 .*LISTENING" >nul 2>&1
if %ERRORLEVEL% equ 0 (
    echo [WARN] Port 3000 is already in use.
    echo        A frontend instance may already be running, or another process is on port 3000.
)

:: -----------------------------------------------------------------------
:: Launch Services in Dedicated Windows
:: -----------------------------------------------------------------------
echo Launching FastAPI Backend on http://localhost:8000 ...
start "ProjectResumeAnalyzer-Backend" /d "%ROOT_DIR%backend" cmd /k "call .venv\Scripts\activate.bat && echo ======================================================== && echo  ProjectResumeAnalyzer - FastAPI Backend                        && echo  URL: http://localhost:8000 - Docs: http://localhost:8000/docs && echo ======================================================== && python -m uvicorn app.main:app --reload --port 8000"

echo Launching Next.js Frontend on http://localhost:3000 ...
start "ProjectResumeAnalyzer-Frontend" /d "%ROOT_DIR%frontend" cmd /k "echo ======================================================== && echo  ProjectResumeAnalyzer - Next.js Frontend                        && echo  URL: http://localhost:3000                                    && echo ======================================================== && call npm run dev"

:: Record state file
echo ACTIVE > "%ROOT_DIR%.run_state"

echo.
echo =====================================================================
echo   ProjectResumeAnalyzer is starting!
echo =====================================================================
echo.
echo   Frontend Application:    http://localhost:3000
echo   Backend API:             http://localhost:8000
echo   Swagger Documentation:   http://localhost:8000/docs
echo.
echo   Two command windows have been opened for the services:
echo     1. "ProjectResumeAnalyzer-Backend"
echo     2. "ProjectResumeAnalyzer-Frontend"
echo.
echo   Leave those windows open while using the application.
echo.
echo   To safely stop both services at any time, run:
echo     stop.bat
echo =====================================================================
echo.
