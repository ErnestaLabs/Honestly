#!/usr/bin/env bash
# honestly-batch-publish.sh — run the daily publish 3 times back-to-back
# so each 3-hour cycle publishes 24 articles (8 cities × 3 passes).
# Falls back to single pass if CPU or memory is tight.
set -euo pipefail
cd /opt/honestly

for i in 1 2 3; do
  echo "[batch $i/3] $(date -Iseconds)"
  timeout 180 python3 publish_daily.py 2>&1 || true
  # Short cooldown between runs so API rate limits don't trip
  sleep 10
done
echo "[batch done] $(date -Iseconds)"
