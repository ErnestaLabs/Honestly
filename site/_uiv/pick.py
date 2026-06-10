import os, json
HERE = os.path.dirname(os.path.abspath(__file__))
rows = [json.loads(l) for l in open(os.path.join(HERE,"index.jsonl"), encoding="utf-8")]

GOOD = {"glass":3,"glassmorphism":3,"gradient":2,"glow":2,"shine":3,"shiny":3,"border":1,
        "animated":1,"animation":1,"smooth":2,"modern":2,"minimal":3,"clean":2,"neumorphism":2,
        "soft":2,"elegant":3,"premium":3,"hover":1,"depth":2,"blur":2,"frosted":3,"underline":2,
        "float":2,"floating":2,"label":2,"search":2,"dots":2,"pulse":2,"progress":2,"shimmer":3,
        "spotlight":2,"sparkle":1,"aurora":2,"wave":1,"loading":1,"toast":2,"success":2,"tooltip":1,
        "segmented":3,"tabs":2,"ios":1,"switch":1,"toggle":1,"3d":1,"flip":1,"reveal":2}
BAD = {"neon":-4,"cyberpunk":-5,"rainbow":-4,"pixel":-4,"retro":-3,"christmas":-6,"halloween":-6,
       "kids":-4,"cartoon":-4,"brutal":-3,"meme":-5,"fire":-3,"matrix":-4,"hacker":-4,"rgb":-3,
       "disco":-4,"skeuomorph":-1,"squid":-3,"valentine":-4,"snow":-3,"galaxy":-1,"star":-1}

def score(tags):
    ts = [t.strip() for t in tags.replace(";",",").split(",") if t.strip()]
    s = 0
    for t in ts:
        for k,v in GOOD.items():
            if k in t: s += v
        for k,v in BAD.items():
            if k in t: s += v
    return s, ts

best = {}
for r in rows:
    sc, ts = score(r["tags"])
    r["score"] = sc
    best.setdefault(r["cat"], []).append(r)

for cat in best:
    best[cat].sort(key=lambda x:-x["score"])
    print(f"\n===== {cat} (top 8 of {len(best[cat])}) =====")
    for r in best[cat][:8]:
        print(f'  {r["score"]:>3}  {r["name"]:<48} :: {r["tags"][:70]}')
