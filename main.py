"""Smart Pantry REST API — run from repo: `cd backend && uvicorn app.main:app --reload`."""

from __future__ import annotations

import logging
import os
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from starlette.responses import Response

from app.api.v1.router import api_router
from app.core.config import dev_cors_origin_regex, settings
from app.core.database import SessionLocal, init_db
from app.core.db_migrate import ensure_schema
from app.services.scheduler_service import start_scheduler, stop_scheduler
from app.services.seed import ensure_recipe_seed_data

logger = logging.getLogger(__name__)


def _run_recipe_seed() -> None:
    db = SessionLocal()
    try:
        summary = ensure_recipe_seed_data(db)
        logger.info("Recipe seed finished: %s", summary)
    except Exception:
        logger.exception("Recipe seed failed")
    finally:
        db.close()


def _deferred_startup() -> None:
    if os.environ.get("SMART_PANTRY_BLOCKING_SEED", "").strip().lower() in ("1", "true", "yes"):
        _run_recipe_seed()
    else:
        threading.Thread(target=_run_recipe_seed, name="recipe-seed", daemon=True).start()
    start_scheduler(expiry_interval_minutes=60)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    ensure_schema()
    threading.Thread(target=_deferred_startup, name="deferred-startup", daemon=True).start()
    yield
    stop_scheduler()


_AUTH_DOCS = (
    "Separated backend for pantry, recipes, and AI recommendations.\n\n"
    "**Authenticate in Swagger (`/docs`):** "
    "1) `POST /api/v1/auth/login` with your email and password — copy `access_token` from the response. "
    "2) Click **Authorize**, paste **only the token** (no `Bearer` prefix; Swagger adds it). "
    "3) Use `GET /api/v1/recipes/{id}` for full instructions, optional Spoonacular step lists, and per-step ingredients/equipment when `SPOONACULAR_API_KEY` is set."
)

app = FastAPI(
    title="Smart Pantry API",
    version="1.0.0",
    description=_AUTH_DOCS,
    lifespan=lifespan,
    swagger_ui_parameters={"persistAuthorization": True},
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins if o.strip()] or ["*"],
    allow_origin_regex=dev_cors_origin_regex(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix="/api/v1")


@app.get("/", include_in_schema=False)
def root():
    """So browsers hitting http://host:8000/ get JSON instead of 404."""
    return {
        "service": "Smart Pantry API",
        "health": "/health",
        "docs": "/docs",
        "openapi": "/openapi.json",
        "api_v1": "/api/v1",
    }


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    """Browsers request this automatically; avoid noisy 404 in logs."""
    return Response(status_code=204)


@app.get("/live", include_in_schema=False)
def live():
    """Fast liveness (no DB) — useful when the process is waking on Render."""
    return {"status": "ok"}


@app.get("/health")
def health():
    """Liveness + DB connectivity so clients only treat the API as up when the database answers."""
    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
    except Exception:
        return JSONResponse(
            status_code=503,
            content={"status": "error", "detail": "database_unavailable"},
        )
    return {"status": "ok"}
