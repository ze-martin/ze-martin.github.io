$ErrorActionPreference = 'Stop'
# Run interactively on the user's PC. Never echo tokens or HTTP error objects.
$root = if ($PSScriptRoot) { Split-Path -Parent $PSScriptRoot } else { (Get-Location).Path }
$folder = Join-Path $root 'data\telegram_private'
try {
    Add-Type -AssemblyName System.Windows.Forms
    $form = New-Object System.Windows.Forms.Form
    $form.Text = 'Conectar Telegram - APUESTAS'
    $form.Width = 550
    $form.Height = 190
    $form.StartPosition = 'CenterScreen'
    $label = New-Object System.Windows.Forms.Label
    $label.Text = 'Pega el token del bot NUEVO de APUESTAS (Ctrl+V):'
    $label.SetBounds(15,15,510,25)
    $box = New-Object System.Windows.Forms.TextBox
    $box.SetBounds(15,45,500,25)
    $box.UseSystemPasswordChar = $true
    $box.ShortcutsEnabled = $true
    $button = New-Object System.Windows.Forms.Button
    $button.Text = 'Continuar'
    $button.SetBounds(390,90,120,30)
    $button.DialogResult = [System.Windows.Forms.DialogResult]::OK
    $form.Controls.AddRange(@($label,$box,$button))
    $form.AcceptButton = $button
    $form.Add_Shown({$box.Focus()})
    if ($form.ShowDialog() -ne [System.Windows.Forms.DialogResult]::OK) { $form.Dispose(); exit 0 }
    if ([string]::IsNullOrWhiteSpace($box.Text)) { $form.Dispose(); throw 'empty' }
    $secret = ConvertTo-SecureString -String $box.Text.Trim() -AsPlainText -Force
    $box.Clear()
    $form.Dispose()
    $ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secret)
    try { $token = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr) }
    finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr) }
    if ($token -notmatch '^\d+:[A-Za-z0-9_-]+$') { throw 'invalid' }
    $base = 'https://api.telegram.org/bot' + $token
    $me = Invoke-RestMethod -Uri ($base + '/getMe') -Method Post -TimeoutSec 20
    if (-not $me.ok) { throw 'invalid' }
    Write-Host ('Bot verificado: @' + $me.result.username)
    if ((Read-Host 'Confirma que es el bot NUEVO de APUESTAS, no BM. Escribe SI').Trim() -ine 'SI') { Write-Host 'Configuración cancelada sin guardar.'; exit 0 }
    $webhook = Invoke-RestMethod -Uri ($base + '/getWebhookInfo') -Method Post -TimeoutSec 20
    if ($webhook.result.url) {
        Write-Host 'Este bot tiene un webhook activo. No se modificó: revisa que sea el bot correcto.'
        exit 1
    }
    $code = 'APUESTAS-' + [Guid]::NewGuid().ToString('N').Substring(0,8)
    Write-Host ('Envía este mensaje a TU bot desde tu chat privado: ' + $code)
    Read-Host 'Después pulsa Enter aquí'
    $updates = Invoke-RestMethod -Uri ($base + '/getUpdates') -Method Post -Body @{timeout=0;limit=100} -TimeoutSec 20
    $matches = @($updates.result | Where-Object { $_.message.chat.type -eq 'private' -and $_.message.text -ceq $code })
    if ($matches.Count -ne 1) {
        Write-Host 'No se encontró una única confirmación. Vuelve a ejecutar el asistente y envía el nuevo código.'
        exit 1
    }
    $chat = [string]$matches[0].message.chat.id
    if ((Read-Host '¿Guardar conexión y enviar UN mensaje de prueba a este chat? Escribe SI').Trim() -ine 'SI') { Write-Host 'Configuración cancelada sin guardar.'; exit 0 }
    New-Item -ItemType Directory -Path $folder -Force | Out-Null
    # DPAPI: only this Windows account on this PC can decrypt the token.
    $secret | ConvertFrom-SecureString | Set-Content -LiteralPath (Join-Path $folder 'token.dpapi') -Encoding UTF8
    @{chat_id=$chat;bot_username=$me.result.username;automatic_notifications_enabled=$false} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $folder 'connection.json') -Encoding UTF8
    $message = @{chat_id=$chat;text='Conexión de APUESTAS verificada. Mensaje de prueba; las alertas automáticas todavía no están activadas.'} | ConvertTo-Json -Compress
    $sent = Invoke-RestMethod -Uri ($base + '/sendMessage') -Method Post -ContentType 'application/json; charset=utf-8' -Body ([Text.Encoding]::UTF8.GetBytes($message)) -TimeoutSec 20
    if (-not $sent.ok) { throw 'send' }
    Write-Host 'Conexión guardada y prueba enviada. Automatización todavía desactivada.'
} catch {
    Write-Host 'No se completó la configuración o la prueba. Verifica token, conexión y código. No compartas el token ni capturas con él.'
    exit 1
} finally {
    $token = $null
    $base = $null
}
