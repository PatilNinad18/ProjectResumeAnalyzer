@echo off
setlocal enabledelayedexpansion

title ProjectResumeAnalyzer - Stopping Services

set "ROOT_DIR=%~dp0"
cd /d "%ROOT_DIR%"

echo =====================================================================
echo   Stopping ProjectResumeAnalyzer Services...
echo =====================================================================
echo.

set "STOPPED=0"

:: 1. Terminate windows by Window Title (terminates cmd + spawned children)
taskkill /FI "WINDOWTITLE eq ProjectResumeAnalyzer-Backend*" /T /F >nul 2>&1
if %ERRORLEVEL% equ 0 set "STOPPED=1"

taskkill /FI "WINDOWTITLE eq ProjectResumeAnalyzer-Frontend*" /T /F >nul 2>&1
if %ERRORLEVEL% equ 0 set "STOPPED=1"

:: 2. Targeted cleanup: safely stop only python/uvicorn on port 8000 and node on port 3000
powershell -NoProfile -Command ^
  "$targets = @( @{Port=8000; Names=@('python','uvicorn')}, @{Port=3000; Names=@('node')} ); " ^
  "foreach ($t in $targets) { " ^
  "  Get-NetTCPConnection -LocalPort $t.Port -State Listen -ErrorAction SilentlyContinue | ForEach-Object { " ^
  "    $proc = Get-Process -Id $_.OwningProcess -ErrorAction SilentlyContinue; " ^
  "    if ($proc -and ($t.Names -contains $proc.ProcessName.ToLower())) { " ^
  "      Write-Host \"  [STOP] Terminating $($proc.ProcessName) (PID $($proc.Id)) on port $($t.Port)...\"; " ^
  "      Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue; " ^
  "    } " ^
  "  } " ^
  "}" >nul 2>&1

if exist "%ROOT_DIR%.run_state" (
    del /f /q "%ROOT_DIR%.run_state" >nul 2>&1
    set "STOPPED=1"
)

echo.
echo =====================================================================
echo   ProjectResumeAnalyzer services have been stopped successfully.
echo =====================================================================
echo.
