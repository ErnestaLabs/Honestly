# run_bot.ps1 - keep the Honestly bot alive 24/7 (while this PC is on).
# Runs bot.py in a loop: if it ever exits or crashes, wait 5s and restart.
# Registered as a Scheduled Task that starts at logon. Logs to bot.log.
$ErrorActionPreference = "Continue"
$dir = "C:\Users\Hello\propertydata"
$py  = "C:\Users\Hello\AppData\Local\Programs\Python\Python313\python.exe"
$log = Join-Path $dir "bot.log"
Set-Location $dir
while ($true) {
    "$(Get-Date -Format s)  starting bot.py" | Add-Content $log
    & $py "$dir\bot.py" *>> $log
    "$(Get-Date -Format s)  bot.py exited (code $LASTEXITCODE) - restarting in 5s" | Add-Content $log
    Start-Sleep -Seconds 5
}
