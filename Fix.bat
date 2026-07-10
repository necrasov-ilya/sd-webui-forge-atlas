@echo off
chcp 65001 >NUL
setlocal
cd /d "%~dp0"

if /I "%~1"=="--check" (
    powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0atlas-fix.ps1" -CheckOnly
) else (
    powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0atlas-fix.ps1"
)

if errorlevel 1 (
    echo.
    echo [Forge Atlas] Recovery failed. See the Russian error above.
    echo.
    pause
    exit /b 1
)

if /I "%~1"=="--check" (
    echo.
    echo [Forge Atlas] Check completed without changes.
    exit /b 0
)
