@echo off
REM run_bot.cmd - keep the Honestly bot alive 24/7 (no admin, no execution policy).
REM Loops: if bot.py exits or crashes, wait 5s and restart. Logs to bot.log.
set DIR=C:\Users\Hello\propertydata
set PY=C:\Users\Hello\AppData\Local\Programs\Python\Python313\python.exe
cd /d "%DIR%"
:loop
echo %date% %time%  starting bot.py >> "%DIR%\bot.log"
"%PY%" "%DIR%\bot.py" >> "%DIR%\bot.log" 2>&1
echo %date% %time%  bot.py exited, restarting in 5s >> "%DIR%\bot.log"
timeout /t 5 /nobreak >nul
goto loop
