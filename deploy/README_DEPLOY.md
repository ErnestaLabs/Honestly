# Deploy Honestly to the VPS (24/7, single instance)

systemd runs exactly one copy and restarts it on crash or reboot. No restart-loop
scripts, no double-polling, no Windows needed once it's up.

## 1. On the VPS (you're SSH'd in as root)
```bash
mkdir -p /opt/honestly/deploy
```

## 2. From your Windows machine, in C:\Users\Hello\propertydata
Upload the bot files and the deploy folder (you'll be asked for the server password):
```powershell
scp bot.py engine.py maps_tools.py cardimg.py .env root@187.77.100.209:/opt/honestly/
scp deploy/honestly.service deploy/setup_vps.sh root@187.77.100.209:/opt/honestly/deploy/
```

## 3. Back on the VPS
```bash
bash /opt/honestly/deploy/setup_vps.sh
```
That installs Python + Pillow, registers the service, and starts it.

## Manage it
```bash
systemctl status honestly      # is it up?
systemctl restart honestly     # after you upload new code
journalctl -u honestly -f      # live logs
```

## When you change code later
Re-upload the changed file(s) with the same scp command, then:
```bash
systemctl restart honestly
```

## Security
- `.env` holds the bot token + API keys. It only lives on the server and your
  machine, never in git (it's gitignored).
- Rotate the VPS root password: it was shared in chat. `passwd` on the server.
- Rotate the Telegram token too if it was ever pasted anywhere public:
  @BotFather -> /revoke, then update `.env` and `systemctl restart honestly`.
