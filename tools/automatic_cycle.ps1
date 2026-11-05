param([switch]$Nightly)
$ErrorActionPreference='Stop'
$root=Split-Path -Parent $PSScriptRoot
Set-Location $root
$env:PYTHONIOENCODING='utf-8'
$env:API_FOOTBALL_CACHE_ENABLED='false'
$mutex=New-Object Threading.Mutex($false,'Local\APUESTAS-AutomaticCycle')
if(-not $mutex.WaitOne(0)){exit 0}
try {
    $tomorrow=[TimeZoneInfo]::ConvertTimeBySystemTimeZoneId([DateTime]::UtcNow,'SA Pacific Standard Time').Date.AddDays(1).ToString('yyyy-MM-dd')
    & python tools/automatic_protocol.py --plan $tomorrow
    if($LASTEXITCODE -ne 0){throw 'plan'}
    if(-not $Nightly){
        & python tools/automatic_protocol.py --tick
        if($LASTEXITCODE -ne 0){throw 'analysis'}
    }
    & powershell.exe -NoProfile -File tools/install_fixture_tasks.ps1
    if($LASTEXITCODE -ne 0){throw 'tasks'}
    & python tools/build_automatic_page.py
    & git add -- automatico.html
    & git diff --cached --quiet -- automatico.html
    if($LASTEXITCODE -ne 0){
        & git commit -m 'Actualizar agenda y capturas automaticas' -- automatico.html
        if($LASTEXITCODE -ne 0){throw 'commit'}
        & git pull --rebase --autostash origin main
        if($LASTEXITCODE -ne 0){throw 'pull'}
        & git push origin main
        if($LASTEXITCODE -ne 0){throw 'push'}
    }
    & python tools/telegram_dispatch.py $(if($Nightly){'--nightly'}else{'--opportunities'})
    if($LASTEXITCODE -ne 0){throw 'telegram'}
} catch {
    Write-Output ('Automatic cycle failed: '+$_.Exception.GetType().Name)
    exit 1
} finally {$mutex.ReleaseMutex();$mutex.Dispose()}
