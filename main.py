"""main.py - FastAPI application entry point.

Wires together all API v1 routers and serves as the uvicorn target
for the Dockerised backend. The existing server.py stdlib server
continues to work for backward compatibility.
"""
from __future__ import annotations

import logging
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Import the v1 routers
from api.v1.properties import router as properties_router
from api.v1.products import router as products_router
from api.v1.community import router as community_router

log = logging.getLogger(__name__)

# ── App initialisation ──────────────────────────────────
app = FastAPI(
    title="Honestly API",
    description="UK property valuation engine — Glass Box AVM, micro-upsells, community Arena",
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


# ── Startup / shutdown ──────────────────────────────────
@app.on_event("startup")
async def startup():
    log.info("Honestly API starting up")


@app.on_event("shutdown")
async def shutdown():
    log.info("Honestly API shutting down")
