# SuperGuard Evolution Cron Job
# Runs every 2 hours: tests, debug, backup to USB, Telegram report

# To install: copy this to a .ps1 file and run as admin, or use Task Scheduler

$Action = New-ScheduledTaskAction -Execute "python.exe" -Argument "-u C:\Users\tomas\AppData\Local\Temp\xfetch\evolution_cycle.py" -WorkingDirectory "C:\Users\tomas\AppData\Local\Temp\xfetch"
$Trigger = New-ScheduledTaskTrigger -RepetitionInterval (New-TimeSpan -Hours 2) -Once -At (Get-Date)
$Settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -RunOnlyIfNetworkAvailable
$Principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest

Register-ScheduledTask -TaskName "SuperGuard_Evolution_2h" -Action $Action -Trigger $Trigger -Settings $Settings -Principal $Principal -Description "SuperGuard Autonomous Evolution: tests, debug, USB backup, Telegram report every 2 hours" -Force

Write-Host "SuperGuard Evolution cron installed successfully"