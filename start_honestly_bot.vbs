' start_honestly_bot.vbs - launch the bot restart-loop with no visible window.
' Placed in the Startup folder so the Honestly bot comes up on every logon.
CreateObject("WScript.Shell").Run """C:\Users\Hello\propertydata\run_bot.cmd""", 0, False
