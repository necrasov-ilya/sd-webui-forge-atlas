@echo off
chcp 65001 >NUL
setlocal
cd /d "%~dp0"

:: set PYTHON=
:: set GIT=
:: set VENV_DIR=

if exist "%~dp0.tools\uv\uv.exe" set "PATH=%~dp0.tools\uv;%PATH%"

powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0atlas-bootstrap.ps1"
if errorlevel 1 (
    echo.
    echo [Forge Atlas] Environment setup failed. See the Russian error above.
    echo.
    pause
    exit /b 1
)

if exist "%~dp0.tools\uv\uv.exe" set "PATH=%~dp0.tools\uv;%PATH%"

set "COMMANDLINE_ARGS=--uv"

:: --xformers --sage --uv
:: --pin-shared-memory --cuda-malloc --cuda-stream
:: --skip-python-version-check --skip-torch-cuda-test --skip-version-check --skip-prepare-environment --skip-install

call webui.bat
