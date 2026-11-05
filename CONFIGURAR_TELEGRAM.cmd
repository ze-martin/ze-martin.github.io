@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
echo Configurando el bot exclusivo de APUESTAS.
echo Se abrira una ventana para pegar el token. No lo pegues en el chat.
powershell.exe -NoProfile -STA -Command "$utf8 = New-Object System.Text.UTF8Encoding($false); [Console]::InputEncoding = $utf8; [Console]::OutputEncoding = $utf8; $OutputEncoding = $utf8; $script = [IO.File]::ReadAllText((Join-Path (Get-Location) 'tools\setup_telegram.ps1'), [Text.Encoding]::UTF8); & ([scriptblock]::Create($script))"
echo.
echo Si no se abrio la ventana, comparte solo el mensaje de error, nunca el token.
pause
endlocal
