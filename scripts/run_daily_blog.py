#!/usr/bin/env python3
"""run_daily_blog.py — cron-ready batch generator for SEO blog articles.

Picks 3 random postcodes from a curated list of high-value UK areas, calls
generate_seo_article.py for each, and logs results to blog_generation.log.

Usage:
  python scripts/run_daily_blog.py
  python scripts/run_daily_blog.py --postcodes M1,B1,L8  # override list
  python scripts/run_daily_blog.py --dry-run              # show what would run
"""
import os
import random
import subprocess
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
SCRIPTS = HERE / "scripts"
LOG_PATH = HERE / "blog_generation.log"

# Curated high-value UK postcode areas (well-represented in the HMLR data)
DEFAULT_POSTCODES = [
    # London
    "SW16", "SE15", "SE23", "SE27", "N22", "SE4", "SE13",
    # Regional cities
    "M1",   # Manchester city centre
    "M15",  # Manchester
    "B1",   # Birmingham city centre
    "B15",  # Birmingham
    "L1",   # Liverpool city centre
    "L8",   # Liverpool
    "LS1",  # Leeds
    "LS6",  # Leeds
    "S1",   # Sheffield
    "S3",   # Sheffield
    "NE1",  # Newcastle
    "NE2",  # Newcastle
    "CF10", # Cardiff
    "CF11", # Cardiff
    "EH1",  # Edinburgh
    "EH2",  # Edinburgh
    "G1",   # Glasgow
    "G3",   # Glasgow
    "BS1",  # Bristol
    "BS8",  # Bristol
    "OX1",  # Oxford
    "OX2",  # Oxford
    "CB1",  # Cambridge
    "CB4",  # Cambridge
]


def log(msg: str):
    """Append a timestamped line to the log file and print to stderr."""
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, file=sys.stderr)
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def generate_article(postcode: str, dry_run: bool = False) -> bool:
    """Run generate_seo_article.py for a single postcode. Returns True on success."""
    script = SCRIPTS / "generate_seo_article.py"
    cmd = [
        sys.executable or "python",
        str(script),
        "--postcode", postcode,
    ]

    if dry_run:
        log(f"[DRY-RUN] Would run: {' '.join(cmd)}")
        return True

    log(f"Generating article for {postcode}...")
    result = subprocess.run(cmd, capture_output=False, text=True, timeout=180)

    if result.returncode == 0:
        log(f"OK: {postcode} — article generated successfully")
        return True
    else:
        log(f"FAIL: {postcode} — exit code {result.returncode}")
        if result.stderr:
            for line in result.stderr.strip().split("\n")[-5:]:
                log(f"  stderr: {line}")
        return False


def main():
    import argparse
    ap = argparse.ArgumentParser(description="Batch generate SEO blog articles from HMLR data")
    ap.add_argument("--postcodes", help="Comma-separated list of postcodes (overrides default)")
    ap.add_argument("--count", type=int, default=3, help="Number of articles to generate (default: 3)")
    ap.add_argument("--dry-run", action="store_true", help="Show what would run without executing")
    args = ap.parse_args()

    if args.postcodes:
        postcodes = [p.strip().upper() for p in args.postcodes.split(",")]
    else:
        postcodes = list(DEFAULT_POSTCODES)

    # Shuffle and pick N
    random.shuffle(postcodes)
    selected = postcodes[:args.count]

    log(f"Starting daily blog run: {args.count} articles from {len(postcodes)} eligible postcodes")
    log(f"Selected: {', '.join(selected)}")

    success_count = 0
    fail_count = 0

    for pc in selected:
        ok = generate_article(pc, dry_run=args.dry_run)
        if ok:
            success_count += 1
        else:
            fail_count += 1

    total = success_count + fail_count
    log(f"Done: {success_count}/{total} articles generated successfully")

    if fail_count > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
