# SuperGuard Alarm - Registry Auto-start
# Run as Administrator to install

$regPath = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run"
$name = "SuperGuardAlarm"
$pythonExe = "C:\Users\tomas\AppData\Local\hermes\hermes-agent\venv\Scripts\python.exe"
$scriptPath = "C:\SuperGuard\panic_mode.py"
$workDir = "C:\SuperGuard"

# Create the command
$command = "`"$pythonExe`" `"$scriptPath`""

# Set registry value
Set-ItemProperty -Path $regPath -Name $name -Value $command -Type String -Force

Write-Host "Registry auto-start configured:"
Write-Host "  Key: $regPath"
Write-Host "  Name: $name"
Write-Host "  Command: $command"
Write-Host "  Working Dir: $workDir"

# Also create a startup shortcut as backup
$startupFolder = [Environment]::GetFolderPath("Startup")
$shortcutPath = Join-Path $startupFolder "SuperGuard Alarm.lnk"
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $pythonExe
$shortcut.Arguments = "`"$scriptPath`""
$shortcut.WorkingDirectory = $workDir
$shortcut.Description = "SuperGuard Alarm - AI Video Surveillance"
$shortcut.Save()

Write-Host "Startup shortcut created: $shortcutPath"
Write-Host ""
Write-Host "To test: run the command manually:"
Write-Host "  $command"