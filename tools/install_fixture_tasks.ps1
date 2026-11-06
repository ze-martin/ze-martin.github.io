$ErrorActionPreference='Stop'
$root=Split-Path -Parent $PSScriptRoot
$python=(Get-Command python).Source
$query="import sqlite3,json; d=sqlite3.connect('data/automatic_protocol.sqlite'); print(json.dumps(sorted(set(k for k,p in d.execute('select kickoff,payload from jobs') if json.loads(p)['fixture']['status']['short']=='NS'))))"
Push-Location $root
try {
    $dates= & $python -c $query | ConvertFrom-Json
    $count=0
    foreach($date in $dates){
        $at=([DateTimeOffset]::Parse($date)).AddHours(-1).LocalDateTime
        if($at -le (Get-Date)){continue}
        $name='APUESTAS-T60-'+$at.ToString('yyyyMMdd-HHmm')
        $action=New-ScheduledTaskAction -Execute 'powershell.exe' -Argument ('-NoProfile -File "'+$root+'\tools\automatic_cycle.ps1"') -WorkingDirectory $root
        $trigger=New-ScheduledTaskTrigger -Once -At $at
        $settings=New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 40) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -WakeToRun
        Register-ScheduledTask -TaskName $name -Action $action -Trigger $trigger -Settings $settings -Description 'Analisis prepartido APUESTAS. No coloca apuestas. Requiere usuario conectado.' -Force | Out-Null
        $count++
    }
    Write-Host ('Tareas por horario instaladas: '+$count)
} finally { Pop-Location }
