param(
    [switch]$CheckOnly
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "Continue"
[Console]::InputEncoding = [System.Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$OutputEncoding = [System.Text.UTF8Encoding]::new($false)

$Root = $PSScriptRoot
$ToolsDir = Join-Path $Root ".tools"
$UvDir = Join-Path $ToolsDir "uv"
$UvLocal = Join-Path $UvDir "uv.exe"
$PythonDir = Join-Path $ToolsDir "python"
$VenvDir = Join-Path $Root "venv"
$VenvPython = Join-Path $VenvDir "Scripts\python.exe"
$PythonVersion = "3.13.12"

function Write-AtlasStep {
    param([string]$Message)
    Write-Host ""
    Write-Host "[Forge Atlas] $Message" -ForegroundColor Cyan
}

function Write-AtlasOk {
    param([string]$Message)
    Write-Host "[Forge Atlas] $Message" -ForegroundColor Green
}

function Invoke-Checked {
    param(
        [string]$Program,
        [string[]]$Arguments,
        [string]$FailureMessage
    )

    & $Program @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "$FailureMessage Код ошибки: $LASTEXITCODE."
    }
}

try {
    Write-AtlasStep "Проверяю наличие uv — менеджера Python и зависимостей."

    $UvPath = $null
    if (Test-Path -LiteralPath $UvLocal) {
        $UvPath = $UvLocal
        Write-AtlasOk "Нашёл локальный uv."
    }
    else {
        $UvCommand = Get-Command "uv" -ErrorAction SilentlyContinue
        if ($null -ne $UvCommand) {
            $UvPath = $UvCommand.Source
            Write-AtlasOk "Нашёл uv в системе."
        }
    }

    if ($null -eq $UvPath) {
        if ($CheckOnly) {
            Write-Host "[Forge Atlas] uv не найден; при обычном запуске он будет установлен локально."
        }
        else {
            Write-AtlasStep "uv не обнаружен. Загружаю официальный установщик Astral."
            New-Item -ItemType Directory -Force -Path $UvDir | Out-Null

            $env:UV_INSTALL_DIR = $UvDir
            $env:UV_NO_MODIFY_PATH = "1"
            $Installer = Invoke-RestMethod -Uri "https://astral.sh/uv/install.ps1" -UseBasicParsing
            Invoke-Expression $Installer

            if (-not (Test-Path -LiteralPath $UvLocal)) {
                throw "Официальный установщик завершился, но файл '$UvLocal' не появился."
            }

            $UvPath = $UvLocal
            Write-AtlasOk "uv установлен локально в папку .tools."
        }
    }

    if ($null -ne $UvPath) {
        Invoke-Checked -Program $UvPath -Arguments @("--version") -FailureMessage "Не удалось запустить uv."
    }

    Write-AtlasStep "Проверяю виртуальное окружение Forge Atlas."

    if (Test-Path -LiteralPath $VenvPython) {
        & $VenvPython -c "import sys; print('.'.join(map(str, sys.version_info[:3])))"
        if ($LASTEXITCODE -eq 0) {
            Write-AtlasOk "Рабочее окружение уже существует — повторно скачивать Python не нужно."
        }
        elseif ($CheckOnly) {
            Write-Host "[Forge Atlas] Существующее окружение повреждено; при обычном запуске оно будет сохранено как резервная копия."
        }
        else {
            $BackupName = "venv.broken-{0}" -f (Get-Date -Format "yyyyMMdd-HHmmss")
            $BackupPath = Join-Path $Root $BackupName
            Write-AtlasStep "Окружение повреждено. Сохраняю его как '$BackupName'."
            Move-Item -LiteralPath $VenvDir -Destination $BackupPath
        }
    }

    if (-not (Test-Path -LiteralPath $VenvPython)) {
        if ($CheckOnly) {
            Write-Host "[Forge Atlas] Окружение не найдено; при обычном запуске будет загружен Python $PythonVersion и создан venv."
        }
        else {
            if ($null -eq $UvPath) {
                throw "Невозможно создать окружение без uv."
            }

            Write-AtlasStep "Окружение не найдено. Подготавливаю Python $PythonVersion."
            Write-Host "[Forge Atlas] Python будет храниться локально в .tools и не заменит системный Python."
            New-Item -ItemType Directory -Force -Path $PythonDir | Out-Null

            $env:UV_PYTHON_INSTALL_DIR = $PythonDir
            $env:UV_CACHE_DIR = Join-Path $Root ".uv-cache"

            Write-AtlasStep "Создаю виртуальное окружение venv. При необходимости uv сначала скачает Python."
            Invoke-Checked `
                -Program $UvPath `
                -Arguments @("venv", $VenvDir, "--python", $PythonVersion, "--seed") `
                -FailureMessage "Не удалось создать виртуальное окружение."

            if (-not (Test-Path -LiteralPath $VenvPython)) {
                throw "Команда uv завершилась без ошибки, но Python в venv не найден."
            }

            Write-AtlasOk "Python и виртуальное окружение готовы."
        }
    }

    if ((Test-Path -LiteralPath $VenvPython) -and -not $CheckOnly) {
        Invoke-Checked `
            -Program $VenvPython `
            -Arguments @("-c", "import sys; print('[Forge Atlas] Python:', sys.version.split()[0])") `
            -FailureMessage "Финальная проверка Python завершилась ошибкой."
    }

    if ($CheckOnly) {
        Write-AtlasOk "Проверка сценария завершена; загрузки и изменения не выполнялись."
    }
    else {
        Write-AtlasOk "Подготовка окружения завершена."
        Write-AtlasStep "Запускаю Forge Atlas."
        Write-Host "[Forge Atlas] При первом запуске зависимости загрузятся автоматически."
        Write-Host "[Forge Atlas] Это может занять продолжительное время — не закрывайте окно."
    }

    exit 0
}
catch {
    Write-Host ""
    Write-Host "[Forge Atlas] Ошибка подготовки окружения:" -ForegroundColor Red
    Write-Host "[Forge Atlas] $($_.Exception.Message)" -ForegroundColor Red
    Write-Host "[Forge Atlas] Проверьте подключение к интернету и свободное место на диске."
    exit 1
}
