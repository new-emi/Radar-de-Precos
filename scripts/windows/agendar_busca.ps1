# agendar_busca.ps1 - cria (ou atualiza) a tarefa "Radar de Precos" no Agendador de Tarefas do Windows.
# Ela roda o buscar_precos.bat todo dia no horario escolhido.
#
# Como usar (PowerShell, dentro da pasta do projeto):
#   powershell -ExecutionPolicy Bypass -File scripts\windows\agendar_busca.ps1            -> todo dia as 11:00
#   powershell -ExecutionPolicy Bypass -File scripts\windows\agendar_busca.ps1 -Hora 19:30
# Para remover:   Unregister-ScheduledTask -TaskName "Radar de Precos"
param([string]$Hora = "11:00")

$bat = Join-Path $PSScriptRoot "buscar_precos.bat"          # este arquivo fica em scripts\windows
$pasta = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)   # raiz do projeto

$acao = New-ScheduledTaskAction -Execute $bat -WorkingDirectory $pasta
$gatilho = New-ScheduledTaskTrigger -Daily -At $Hora
# StartWhenAvailable: se o PC estava desligado no horario, roda assim que ligar
$config = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
          -ExecutionTimeLimit (New-TimeSpan -Hours 1)

Register-ScheduledTask -TaskName "Radar de Precos" -Action $acao -Trigger $gatilho -Settings $config `
    -Description "Busca os precos da lista de compras e guarda no historico (Radar de Precos)" -Force | Out-Null

Write-Host ""
Write-Host "Pronto! A busca vai rodar todo dia as $Hora." -ForegroundColor Green
Write-Host "Para testar agora:  Start-ScheduledTask -TaskName 'Radar de Precos'"
Write-Host "O registro de cada busca fica em busca_automatica.log"
