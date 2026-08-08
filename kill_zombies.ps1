$mypid = 18220
Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
Where-Object { $_.CommandLine -match '(panic_mode|main\.py|superguard)' -and $_.ProcessId -ne $mypid } |
ForEach-Object { Stop-Process -Id $_.ProcessId -Force; Write-Output ('killed ' + $_.ProcessId) }
