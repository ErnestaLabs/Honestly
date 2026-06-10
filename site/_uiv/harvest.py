import os, re, sys, json, urllib.request
from concurrent.futures import ThreadPoolExecutor

BASE = "https://raw.githubusercontent.com/uiverse-io/galaxy/main"
HERE = os.path.dirname(os.path.abspath(__file__))

# category -> how many files to sample (None = all)
PLAN = {
    "Inputs": None, "Toggle-switches": None, "Tooltips": None,
    "Notifications": None, "Forms": None, "loaders": 260,
    "Buttons": 320, "Cards": 320,
}

TAG_RE = re.compile(r"Tags:\s*([^\*\n/]+)", re.I)

def fetch(cat, name):
    url = f"{BASE}/{cat}/{urllib.parse.quote(name)}"
    try:
        with urllib.request.urlopen(url, timeout=20) as r:
            html = r.read().decode("utf-8", "replace")
    except Exception:
        return None
    m = TAG_RE.search(html)
    tags = m.group(1).strip().lower() if m else ""
    has_tw = 'class="' in html and ('bg-' in html or 'rounded' in html) and "<style" not in html
    return {"cat": cat, "name": name, "tags": tags, "len": len(html), "tw": has_tw}

jobs = []
for cat, n in PLAN.items():
    lp = os.path.join(HERE, f"{cat}.list")
    if not os.path.exists(lp):
        continue
    names = [x.strip() for x in open(lp, encoding="utf-8") if x.strip()]
    if n:
        names = names[:n]
    for nm in names:
        jobs.append((cat, nm))

print(f"fetching {len(jobs)} files...", file=sys.stderr)
out = []
with ThreadPoolExecutor(max_workers=24) as ex:
    for res in ex.map(lambda a: fetch(*a), jobs):
        if res:
            out.append(res)

with open(os.path.join(HERE, "index.jsonl"), "w", encoding="utf-8") as f:
    for r in out:
        f.write(json.dumps(r) + "\n")
print(f"harvested {len(out)} with tags", file=sys.stderr)
