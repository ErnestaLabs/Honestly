"""main.py - FastAPI application entry point.

Wires together all API v1 routers and serves as the uvicorn target
for the Dockerised backend. The existing server.py stdlib server
continues to work for backward compatibility.

- Automates the daily SEO blog generation via APScheduler (2 AM)
- Enforces Telegram-only access via initData middleware
- Redis-backed distributed lock for single-scheduler semantics
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import os
import subprocess
import sys
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

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

# ── Telegram initData middleware ────────────────────────
# All API requests must come from the Telegram client.
# The bot token is loaded from env (set in .env / Docker env_file).
# Exempt: health check, OpenAPI docs.

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")

# Endpoints that don't need Telegram validation
EXEMPT_PATHS = {"/health", "/docs", "/redoc", "/openapi.json", "/favicon.ico"}


@app.middleware("http")
async def telegram_initdata_middleware(request: Request, call_next):
    """Reject requests that do not carry valid Telegram WebApp initData.

    The Telegram Mini App passes initData in the URL hash. Nginx forwards
    it as the X-Telegram-Init-Data header. We verify the HMAC-SHA256
    signature using the bot token as the secret key.
    """
    path = request.url.path

    # Allow exempt paths through
    if path in EXEMPT_PATHS or path.startswith("/api/community/") or path.startswith("/api/properties/"):
        pass  # still check below for validate endpoints

    # Health check is always open
    if path == "/health":
        return await call_next(request)

    # Get initData from header (set by nginx) or query param
    init_data = request.headers.get("X-Telegram-Init-Data", "")
    if not init_data:
        init_data = request.query_params.get("initData", "")
    if not init_data:
        # Try to get from Telegram-Init-Data (standard header name)
        init_data = request.headers.get("Telegram-Init-Data", "")

    # If no initData and not an exempt path, block
    if not init_data:
        # Allow non-sensitive endpoints through (blog, public pages)
        if path.startswith("/blog") or path == "/sitemap.xml" or path == "/robots.txt":
            return await call_next(request)
        # Everything else (API) requires Telegram
        return JSONResponse(
            status_code=403,
            content={"ok": False, "reason": "Telegram-only. Access via @usehonestly_bot"},
        )

    # Validate initData signature
    if TELEGRAM_BOT_TOKEN and _validate_telegram_init_data(init_data):
        return await call_next(request)
    elif not TELEGRAM_BOT_TOKEN:
        # No token configured = dev mode, pass through
        return await call_next(request)
    else:
        return JSONResponse(
            status_code=403,
            content={"ok": False, "reason": "Invalid Telegram session"},
        )


def _validate_telegram_init_data(init_data: str) -> bool:
    """Validate Telegram WebApp initData HMAC-SHA256 signature.

    The initData string looks like:
      query_id=...&auth_date=...&hash=...&user=...

    Algorithm:
      1. Extract the 'hash' field.
      2. Sort remaining fields alphabetically.
      3. Join with \\n into a data-check-string.
      4. Compute HMAC-SHA256 of data-check-string using
         HMAC-SHA256('WebAppData', bot_token) as the secret.
      5. Compare computed hash == extracted hash (constant-time).
    """
    import urllib.parse

    try:
        params = urllib.parse.parse_qs(init_data, keep_blank_values=True)
    except Exception:
        return False

    # Extract the hash
    hash_values = params.pop("hash", None)
    if not hash_values:
        return False
    received_hash = hash_values[0]

    # Build data-check-string: all other fields sorted alphabetically
    # Each field is key=value, joined by \\n
    sorted_keys = sorted(params.keys())
    data_check_parts = []
    for key in sorted_keys:
        # Take the last value for each key (like Telegram does)
        val = params[key][-1]
        data_check_parts.append(f"{key}={val}")
    data_check_string = "\\n".join(data_check_parts)

    # Compute secret: HMAC-SHA256("WebAppData", bot_token)
    secret_key = hmac.new(
        b"WebAppData",
        TELEGRAM_BOT_TOKEN.encode("utf-8"),
        hashlib.sha256,
    ).digest()

    # Compute expected hash
    computed_hash = hmac.new(
        secret_key,
        data_check_string.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    # Constant-time compare
    return hmac.compare_digest(computed_hash, received_hash)


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
