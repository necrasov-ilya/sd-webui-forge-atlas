param(
    [switch]$CheckOnly
)

$ErrorActionPreference = "Stop"
[Console]::InputEncoding = [System.Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$OutputEncoding = [System.Text.UTF8Encoding]::new($false)

$Root = $PSScriptRoot
$RepairDir = Join-Path $Root "tmp\atlas-repair"
$AtlasOriginPattern = "(?i)github\.com[:/]necrasov-ilya/sd-webui-forge-atlas(?:\.git)?/?$"
$AtlasLinkName = "Atlas Library"
$AtlasModelFolders = @("Stable-diffusion", "VAE", "text_encoder", "Lora", "ESRGAN", "ControlNet", "embeddings")
$ProtectedPaths = @(
    "models/.forge-atlas-protected",
    "outputs/.forge-atlas-protected",
    "output/.forge-atlas-protected",
    "venv/.forge-atlas-protected",
    ".tools/.forge-atlas-protected",
    "extensions/.forge-atlas-protected",
    "embeddings/.forge-atlas-protected",
    "config.json",
    "ui-config.json",
    "user.css"
)

function Write-AtlasStep {
    param([string]$Message)
    Write-Host ""
    Write-Host "[Forge Atlas] $Message" -ForegroundColor Cyan
}

function Write-AtlasOk {
    param([string]$Message)
    Write-Host "[Forge Atlas] $Message" -ForegroundColor Green
}

function Invoke-GitChecked {
    param(
        [string[]]$Arguments,
        [string]$FailureMessage
    )

    & git @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "$FailureMessage Код ошибки Git: $LASTEXITCODE."
    }
}

function Get-AtlasResetTargets {
    $Targets = @()
    foreach ($Folder in $AtlasModelFolders) {
        $Targets += Join-Path $Root ("models\{0}\{1}" -f $Folder, $AtlasLinkName)
    }
    return $Targets
}

function Remove-AtlasLibraryLinks {
    $Removed = 0
    foreach ($LinkPath in (Get-AtlasResetTargets)) {
        $Item = Get-Item -LiteralPath $LinkPath -Force -ErrorAction SilentlyContinue
        if ($null -eq $Item) {
            continue
        }

        $IsLink = ($Item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0
        if ($IsLink) {
            Remove-Item -LiteralPath $LinkPath -Force
            $Removed++
            continue
        }

        $HasContents = $null -ne (Get-ChildItem -LiteralPath $LinkPath -Force | Select-Object -First 1)
        if (-not $HasContents) {
            Remove-Item -LiteralPath $LinkPath -Force
            $Removed++
        }
        else {
            Write-Host "[Forge Atlas] Пропускаю '$LinkPath': это непустая обычная папка, а не ссылка Atlas." -ForegroundColor Yellow
        }
    }
    return $Removed
}

function Remove-AtlasVenv {
    $VenvPath = [System.IO.Path]::GetFullPath((Join-Path $Root "venv"))
    $ExpectedPath = [System.IO.Path]::GetFullPath("$Root\venv")
    if ($VenvPath -ne $ExpectedPath -or -not $VenvPath.StartsWith("$([System.IO.Path]::GetFullPath($Root))\", [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Небезопасный путь виртуального окружения: '$VenvPath'. Удаление отменено."
    }
    if (Test-Path -LiteralPath $VenvPath) {
        Remove-Item -LiteralPath $VenvPath -Recurse -Force
        return $true
    }
    return $false
}

try {
    Set-Location -LiteralPath $Root

    Write-AtlasStep "Проверяю Git-репозиторий."
    if ($null -eq (Get-Command "git" -ErrorAction SilentlyContinue)) {
        throw "Git не найден. Установите Git и снова запустите Fix.bat."
    }

    & git rev-parse --is-inside-work-tree *> $null
    if ($LASTEXITCODE -ne 0) {
        throw "Папка Forge Atlas не является рабочим Git-репозиторием."
    }

    $OriginUrl = (& git remote get-url origin).Trim()
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($OriginUrl)) {
        throw "Не удалось определить адрес origin. Восстановление из сети отменено."
    }
    if ($OriginUrl -notmatch $AtlasOriginPattern) {
        throw "origin указывает не на Forge Atlas: '$OriginUrl'. Ожидался necrasov-ilya/sd-webui-forge-atlas."
    }
    Write-AtlasOk "Источник обновлений: $OriginUrl"

    Write-AtlasStep "Проверяю защиту пользовательских данных."
    foreach ($Path in $ProtectedPaths) {
        & git check-ignore -q -- $Path
        if ($LASTEXITCODE -ne 0) {
            throw "Путь '$Path' не защищён правилами .gitignore. Очистка отменена."
        }
    }
    Write-AtlasOk "Модели, outputs, настройки, расширения и локальные инструменты защищены. venv будет создан заново."

    $CurrentCommit = (& git rev-parse HEAD).Trim()
    if ($LASTEXITCODE -ne 0) {
        throw "Не удалось определить текущую версию Forge Atlas."
    }

    $Status = @(& git status --short)
    if ($LASTEXITCODE -ne 0) {
        throw "Не удалось проверить изменения рабочей папки."
    }

    if ($CheckOnly) {
        Write-Host "[Forge Atlas] Текущая версия: $CurrentCommit"
        if ($Status.Count -gt 0) {
            Write-Host "[Forge Atlas] Найдены изменения, которые обычный Fix.bat сначала сохранит в Git stash:"
            $Status | ForEach-Object { Write-Host "  $_" }
        }
        else {
            Write-Host "[Forge Atlas] Рабочая папка уже чистая."
        }
        $ExistingLinks = @((Get-AtlasResetTargets) | Where-Object { $null -ne (Get-Item -LiteralPath $_ -Force -ErrorAction SilentlyContinue) })
        Write-Host "[Forge Atlas] Reset удалит служебных ссылок/пустых каталогов Atlas Library: $($ExistingLinks.Count)."
        Write-Host "[Forge Atlas] Reset удалит venv: $(if (Test-Path -LiteralPath (Join-Path $Root 'venv')) { 'да' } else { 'нет' })."
        Write-AtlasOk "Проверка восстановления завершена; файлы не изменялись."
        exit 0
    }

    New-Item -ItemType Directory -Force -Path $RepairDir | Out-Null
    $Stamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $SnapshotPath = Join-Path $RepairDir "before-fix-$Stamp.txt"
    @(
        "Commit: $CurrentCommit"
        "Date: $(Get-Date -Format o)"
        ""
        "Working tree:"
        $Status
    ) | Set-Content -LiteralPath $SnapshotPath -Encoding UTF8

    if ($Status.Count -gt 0) {
        Write-AtlasStep "Сохраняю текущие изменения в резервный Git stash."
        Invoke-GitChecked `
            -Arguments @("stash", "push", "--include-untracked", "-m", "Forge Atlas Fix backup $Stamp") `
            -FailureMessage "Не удалось сохранить изменения перед восстановлением."
        Write-AtlasOk "Изменения сохранены и при необходимости могут быть восстановлены из Git stash."
    }
    else {
        Write-AtlasOk "Несохранённых изменений нет."
    }

    Write-AtlasStep "Проверяю последнюю опубликованную версию Forge Atlas."
    & git fetch origin neo --prune
    if ($LASTEXITCODE -eq 0) {
        $Target = "origin/neo"
        Write-AtlasOk "Обновления получены из вашего репозитория Forge Atlas."
    }
    else {
        $Target = "HEAD"
        Write-Host "[Forge Atlas] Интернет или origin недоступны; восстанавливаю текущую установленную версию." -ForegroundColor Yellow
    }

    Write-AtlasStep "Возвращаю файлы программы к версии $Target."
    Invoke-GitChecked `
        -Arguments @("reset", "--hard", $Target) `
        -FailureMessage "Не удалось восстановить отслеживаемые файлы."

    Write-AtlasStep "Убираю оставшиеся неотслеживаемые файлы программы."
    Write-Host "[Forge Atlas] Игнорируемые пользовательские данные не затрагиваются."
    Invoke-GitChecked `
        -Arguments @("clean", "-f", "-d") `
        -FailureMessage "Не удалось очистить неотслеживаемые файлы программы."

    Write-AtlasStep "Сбрасываю подключённые библиотеки моделей."
    $RemovedLinks = Remove-AtlasLibraryLinks
    Write-AtlasOk "Удалено служебных ссылок/пустых каталогов Atlas Library: $RemovedLinks. Внешние модели не затронуты."

    Write-AtlasStep "Удаляю виртуальное окружение для чистой переустановки."
    if (Remove-AtlasVenv) {
        Write-AtlasOk "venv удалён. При запуске Forge Atlas создаст его заново."
    }
    else {
        Write-AtlasOk "venv уже отсутствует. При запуске Forge Atlas создаст его заново."
    }

    $FinalStatus = @(& git status --short)
    if ($LASTEXITCODE -ne 0 -or $FinalStatus.Count -gt 0) {
        throw "После восстановления рабочая папка всё ещё содержит изменения."
    }

    $FinalCommit = (& git rev-parse HEAD).Trim()
    Write-AtlasOk "Рабочая папка восстановлена. Версия: $FinalCommit"
    Write-Host "[Forge Atlas] Диагностическая запись: $SnapshotPath"

    Write-AtlasStep "Запускаю восстановленный Forge Atlas."
    & "$env:ComSpec" /d /c "call `"$Root\webui-user.bat`""
    exit $LASTEXITCODE
}
catch {
    Write-Host ""
    Write-Host "[Forge Atlas] Ошибка восстановления:" -ForegroundColor Red
    Write-Host "[Forge Atlas] $($_.Exception.Message)" -ForegroundColor Red
    Write-Host "[Forge Atlas] Внешние модели и outputs не удалялись."
    exit 1
}
