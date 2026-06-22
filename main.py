"""main.py - FastAPI application entry point.

Wires together all API v1 routers and serves as the uvicorn target
for the Dockerised backend. The existing server.py stdlib server
continues to work for backward compatibility.

Automates the daily SEO blog generation via APScheduler (runs at 2 AM)
with a Redis-backed distributed lock so only one uvicorn worker fires it.
"""
from __future__ import annotations

import logging
import os
import subprocess
import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Import the v1 routers
from api.v1.properties import router as properties_router
from api.v1.products import router as products_router
from api.v1.community import router as community_router

# ── APScheduler (daily blog automation) ─────────────────
HERE = Path(__file__).resolve().parent
BLOG_SCRIPT = HERE / "scripts" / "run_daily_blog.py"

log = logging.getLogger(__name__)

# ── App initialisation ──────────────────────────────────
app = FastAPI(
    title="Honestly API",
    description="UK property valuation engine \u2014 Glass Box AVM, micro-upsells, community Arena",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# ── CORS (allow the Telegram Mini App + production domain) ──
ALLOWED_ORIGINS = os.environ.get(
    "CORS_ORIGINS",
    "https://usehonestly.co.uk,https://t.me,https://web.telegram.org",
).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Register routers ────────────────────────────────────
app.include_router(properties_router, prefix="/api")
app.include_router(products_router, prefix="/api")
app.include_router(community_router, prefix="/api")


# ── Health check ────────────────────────────────────────
@app.get("/health")
def health():
    """Simple health check for the load balancer / Docker health check."""
    return {"ok": True, "service": "honestly-api"}


# ── Daily blog job ──────────────────────────────────────
def run_daily_blog():
    """Shell out to run_daily_blog.py. Logs but never crashes the scheduler."""
    if not BLOG_SCRIPT.exists():
        log.warning("Blog script not found at %s, skipping daily run", BLOG_SCRIPT)
        return
    try:
        result = subprocess.run(
            [sys.executable, str(BLOG_SCRIPT)],
            capture_output=True,
            text=True,
            timeout=600,
            cwd=str(HERE),
        )
        if result.returncode == 0:
            log.info("Daily blog generation OK")
        else:
            log.warning(
                "Daily blog generation failed (exit %d): %s",
                result.returncode,
                result.stderr[-500:] if result.stderr else "no stderr",
            )
    except subprocess.TimeoutExpired:
        log.warning("Daily blog generation timed out after 10 minutes")
    except Exception as exc:
        log.warning("Daily blog generation error: %s", exc)


# ── Scheduler lock (prevent duplicate workers) ──────────
def _try_acquire_lock() -> bool:
    """Try to acquire a distributed lock so only one uvicorn worker schedules the blog.

    Strategy:
      1. Redis SETNX (preferred \u2014 Redis is part of the Docker stack)
      2. File-based fallback (for local dev without Redis)
    """
    # Try Redis first
    redis_url = os.environ.get("REDIS_URL", "redis://redis:6379/0")
    try:
        import redis as redis_mod
        r = redis_mod.Redis.from_url(redis_url, socket_connect_timeout=3)
        acquired = r.setnx("scheduler:lock:daily_blog", "1")
        if acquired:
            r.expire("scheduler:lock:daily_blog", 7200)  # 2-hour lease
            log.info("Scheduler lock acquired via Redis")
            return True
        log.debug("Scheduler lock held by another worker (Redis)")
        return False
    except Exception:
        pass

    # Fallback: file-based lock in /tmp (works in single-container setups)
    lock_path = Path("/tmp/honestly_scheduler.lock")
    if not lock_path.exists():
        try:
            lock_path.write_text("1")
            log.info("Scheduler lock acquired via file lock")
            return True
        except OSError:
            pass
    return False


# ── Startup / shutdown ──────────────────────────────────
@app.on_event("startup")
async def startup():
    log.info("Honestly API starting up")
    _init_blog_scheduler()


def _init_blog_scheduler():
    """Initialise the APScheduler for daily blog generation.

    Only the first uvicorn worker to grab the distributed lock will
    run the scheduler. This prevents 4 simultaneous 2 AM runs.
    """
    if not _try_acquire_lock():
        return

    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        from apscheduler.triggers.cron import CronTrigger

        scheduler = BackgroundScheduler(
            daemon=True,
            job_defaults={
                "coalesce": True,       # skip missed runs if container was down
                "max_instances": 1,
                "misfire_grace_time": 3600,  # 1 hour grace
            },
        )
        scheduler.add_job(
            func=run_daily_blog,
            trigger=CronTrigger(hour=2, minute=0),
            id="daily_blog_generation",
            replace_existing=True,
            name="Daily SEO Blog Generation",
        )
        scheduler.start()
        log.info("Daily blog scheduler started (02:00 UTC)")

        # Store on app state for graceful shutdown
        app.state.scheduler = scheduler
    except Exception as exc:
        log.warning("Could not start APScheduler: %s", exc)


@app.on_event("shutdown")
async def shutdown():
    log.info("Honestly API shutting down")
    scheduler = getattr(app.state, "scheduler", None)
    if scheduler and scheduler.running:
        scheduler.shutdown(wait=False)
        log.info("Daily blog scheduler shut down")
