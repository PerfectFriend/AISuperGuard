# SuperGuard Alarm - Task Scheduler Auto-start (Most Robust)
# Run as Administrator

$taskName = "SuperGuardAlarm"
$pythonExe = "C:\Users\tomas\AppData\Local\hermes\hermes-agent\venv\Scripts\python.exe"
$scriptPath = "C:\SuperGuard\panic_mode.py"
$workDir = "C:\SuperGuard"

# Delete existing task if exists
$existingTask = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
if ($existingTask) {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
    Write-Host "Removed existing task: $taskName"
}

# Create action
$action = New-ScheduledTaskAction -Execute $pythonExe -Argument "`"$scriptPath`"" -WorkingDirectory $workDir

# Create trigger - At startup
$trigger = New-ScheduledTaskTrigger -AtStartup

# Create settings
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit (New-TimeSpan -Hours 0) `
    -Hidden $false

# Create principal (run as current user with highest privileges)
$principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest

# Register task
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Force

Write-Host "Task Scheduler auto-start configured:"
Write-Host "  Task Name: $taskName"
Write-Host "  Trigger: At System Startup"
Write-Host "  Action: $pythonExe $scriptPath"
Write-Host "  Working Dir: $workDir"
Write-Host "  Run Level: Highest (SYSTEM)"
Write-Host "  Auto-restart: Yes (3 retries, 1 min interval)"
Write-Host ""
Write-Host "To manage:"
Write-Host "  Start:   Start-ScheduledTask -TaskName '$taskName'"
Write-Host "  Stop:    Stop-ScheduledTask -TaskName '$taskName'"
Write-Host "  Status:  Get-ScheduledTask -TaskName '$taskName'"
Write-Host "  Logs:    Event Viewer > Task Scheduler > Microsoft > Windows > TaskScheduler"