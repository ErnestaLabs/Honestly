#!/usr/bin/env bash
# Run this ON the VPS as root, after the project files are in /opt/honestly.
# It installs Python, registers the bot as a systemd service (single instance,
# auto-restart, starts on boot), and launches it.
set -euo pipefail

APP=/opt/honestly
echo "==> checking files in $APP"
for f in bot.py engine.py appraise.py maps_tools.py cardimg.py report.py .env; do
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

echo "==> installing systemd unit"
cp "$APP/deploy/honestly.service" /etc/systemd/system/honestly.service
systemctl daemon-reload
systemctl enable honestly.service
systemctl restart honestly.service
sleep 4
systemctl --no-pager status honestly.service | head -n 12
echo "==> done. logs: journalctl -u honestly -f  (or tail -f /var/log/honestly.log)"
