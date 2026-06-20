"""FastAPI entrypoint. Wires middleware, the admin API, and the Radar worker."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.api.routes import router
from app.config import get_settings
from app.database import init_db
from app.radar.worker import radar_loop

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("shirtpost")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    init_db()
    stop_event = asyncio.Event()
    task: asyncio.Task | None = None
    if settings.radar_enabled:
        task = asyncio.create_task(radar_loop(stop_event))
    else:
        logger.info("radar disabled (RADAR_ENABLED=false)")
    try:
        yield
    finally:
        stop_event.set()
        if task is not None:
            try:
                await asyncio.wait_for(task, timeout=10)
            except asyncio.TimeoutError:
                logger.warning("radar loop did not stop within 10s")


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="ShirtPost Radar API", version="0.1.0", lifespan=lifespan)

    # TrustedHostMiddleware: interim mitigation for CVE-2026-48710 (BadHost).
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.allowed_hosts)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.admin_cors_origins,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )
    app.include_router(router, prefix="/api")

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
