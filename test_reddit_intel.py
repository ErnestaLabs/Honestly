"""Test reddit_intel module works end-to-end."""
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import reddit_intel, json

# Test health
h = reddit_intel._call_mcp("hit_health", {})
if h and h.get("raw"):
    print("HEALTH: OK -", h["raw"][:100])
else:
    print("HEALTH: FAILED")
    sys.exit(1)

# Test area scan
intel = reddit_intel.for_area("SE15", audience="buyer")
print("INTEL:", json.dumps(intel, indent=2, default=str)[:2000])
print()
brief = reddit_intel.format_brief(intel)
print("BRIEF:", brief[:1000] if brief else "(empty)")
