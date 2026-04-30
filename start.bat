@echo off
REM Bhuvana's Pit Wall — start script (Windows)
REM Usage: double-click this file, or run from Command Prompt

cd /d "%~dp0"

echo.
echo   Bhuvana's Pit Wall -- setup check
echo   ==================================

REM Try 'py' (Windows Python Launcher — most reliable), then 'python', then 'python3'
set PYTHON=

where py >nul 2>&1
if not errorlevel 1 (
    set PYTHON=py
    goto :found
)

where python >nul 2>&1
if not errorlevel 1 (
    set PYTHON=python
    goto :found
)

where python3 >nul 2>&1
if not errorlevel 1 (
    set PYTHON=python3
    goto :found
)

echo.
echo   ERROR: Python not found.
echo.
echo   Please install Python 3.9+ from:
echo     https://www.python.org/downloads/
echo.
echo   IMPORTANT: During install, tick "Add Python to PATH"
echo.
pause
exit /b 1

:found
echo   Python found: %PYTHON%
for /f "tokens=*" %%v in ('%PYTHON% --version 2^>^&1') do echo   Version: %%v

echo.
echo   Installing dependencies (this may take a minute first time)...
%PYTHON% -m pip install -q -r requirements.txt
if errorlevel 1 (
    echo.
    echo   pip install failed. Try running as Administrator,
    echo   or open a terminal and run:
    echo     %PYTHON% -m pip install -r requirements.txt
    pause
    exit /b 1
)

echo.
echo   Starting server at http://localhost:5000
echo   (Close this window to stop the server)
echo.

REM Open browser after short delay
start "" /b cmd /c "timeout /t 3 >nul && start http://localhost:5000"

%PYTHON% server.py
pause
