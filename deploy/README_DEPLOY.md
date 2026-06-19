# Deploy Honestly to the VPS (24/7, single instance)

systemd runs one Telegram bot service and one web service, both restarted by systemd on crash or reboot. No restart-loop scripts, no double-polling, no Windows needed once it's up.

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
That installs Python + Pillow, registers the bot and web services, and starts them.

## Manage it
```bash
systemctl status honestly honestly-web      # are bot + web up?
systemctl restart honestly honestly-web     # after you upload new code
journalctl -u honestly -f                   # live bot logs
journalctl -u honestly-web -f               # live web logs
```

## When you change code later
Re-upload the changed file(s) with the same scp command, then:
```bash
systemctl restart honestly honestly-web
```

Current web service:

- `honestly-web.service` runs `server.py --port 8080`.
- `honestly-web.service` listens on `http://127.0.0.1:8080` / public `http://187.77.100.209:8080`.
- Production HTTPS origin is live via nginx + Let's Encrypt at `https://usehonestly.co.uk` and `https://www.usehonestly.co.uk`.
- `HONESTLY_PUBLIC_URL` and `HONESTLY_WEBAPP_URL` are set to `https://usehonestly.co.uk` so hosted report links and Telegram Mini App launch work.
- Temporary sslip.io origin was used during setup only; production should use the real domain.

## Daily blog (auto-publish one district per city, every morning)

The blog publishes itself: a systemd timer runs `publish_daily.py` once a day, which picks
the next postcode district in each city's rotation, gathers that district's OWN live data,
renders the SEO/AEO page, stores it, and rebuilds the index/hubs/sitemap/feed. `server.py`
serves the static tree at `/blog/`, `/blog/city/<slug>/`, `/blog/<city>-<district>/`,
`/sitemap.xml`, `/robots.txt` and `/blog/feed.xml`.

Upload the new files and the timer units:
```powershell
scp publish_daily.py blog.py cities.py market_district.py geo.py area_context.py `
    land_registry.py store.py server.py root@187.77.100.209:/opt/honestly/
scp deploy/honestly-blog.service deploy/honestly-blog.timer root@187.77.100.209:/opt/honestly/deploy/
```
On the VPS, register and start the timer (one time):
```bash
cp /opt/honestly/deploy/honestly-blog.{service,timer} /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now honestly-blog.timer
```
Manage it:
```bash
systemctl list-timers honestly-blog        # when does it next fire?
systemctl start honestly-blog.service      # publish now, off-schedule
journalctl -u honestly-blog -f             # live publish logs
```
The site directory (`/opt/honestly/site/`) and the SQLite DB hold the generated pages and
models; back them up with the rest of `/opt/honestly`.

## Security
- `.env` holds the bot token + API keys. It only lives on the server and your
  machine, never in git (it's gitignored).
- Rotate the VPS root password: it was shared in chat. `passwd` on the server.
- Rotate the Telegram token too if it was ever pasted anywhere public:
  @BotFather -> /revoke, then update `.env` and `systemctl restart honestly`.
