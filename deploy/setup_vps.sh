#!/usr/bin/env bash
# Run this ON the VPS as root, after the project files are in /opt/honestly.
# It installs Python, registers the bot as a systemd service (single instance,
# auto-restart, starts on boot), and launches it.
set -euo pipefail

APP=/opt/honestly
echo "==> checking files in $APP"
for f in bot.py server.py engine.py appraise.py maps_tools.py cardimg.py report.py webapp/index.html .env; do
  [ -f "$APP/$f" ] || { echo "MISSING $APP/$f - upload it first (see deploy notes)"; exit 1; }
done

echo "==> installing python3"
if command -v apt-get >/dev/null; then
  apt-get update -y && apt-get install -y python3 python3-pip
elif command -v dnf >/dev/null; then
  dnf install -y python3 python3-pip
fi

# The engine is stdlib-only; cardimg needs Pillow for the blurred card image;
# report.py needs fpdf2 to build the detailed PDF deliverable (pure Python, no
# browser or system libraries - so it runs on this memory-constrained box).
echo "==> installing Pillow + fpdf2 (card images + PDF report)"
python3 -m pip install --quiet --break-system-packages Pillow fpdf2 || python3 -m pip install --quiet Pillow fpdf2 || true

# Blog comments are self-hosted with Remark42 (open-source, MIT) in its own Docker container -
# anonymous by default, optional Google/GitHub/email/Telegram sign-in, our box, our data. It is
# a SEPARATE stand-up (DNS + container + nginx subdomain), documented in deploy/remark42/README.md.
# The blog only renders the widget once REMARK_URL is set in this .env, so there's nothing to
# install here - set REMARK_URL + REMARK_SITE after Remark42 is up and rebuild the blog.

echo "==> installing systemd units"
cp "$APP/deploy/honestly.service" /etc/systemd/system/honestly.service
cp "$APP/deploy/honestly-web.service" /etc/systemd/system/honestly-web.service
systemctl daemon-reload
systemctl enable honestly.service honestly-web.service
systemctl restart honestly.service honestly-web.service
sleep 4
systemctl --no-pager status honestly.service | head -n 12
systemctl --no-pager status honestly-web.service | head -n 12
echo "==> done. bot logs: journalctl -u honestly -f  (or tail -f /var/log/honestly.log)"
echo "==> done. web logs: journalctl -u honestly-web -f  (or tail -f /var/log/honestly-web.log)"
