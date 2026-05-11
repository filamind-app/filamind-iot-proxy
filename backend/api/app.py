"""FastAPI app factory + lifespan.

Migrations are NOT run from here — Alembic is run by the operator out
of band (or from a one-shot init container in production).
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI

from api.config import get_settings
from api.routes import admin, health, pairing


def _configure_logging(level: str) -> None:
    logging.basicConfig(level=getattr(logging, level.upper(), logging.INFO))
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, level.upper(), logging.INFO),
        ),
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    s = get_settings()
    _configure_logging(s.log_level)
    log = structlog.get_logger("api")
    log.info("startup", proxy_public_url=s.proxy_public_url)
    yield
    log.info("shutdown")


def create_app() -> FastAPI:
    app = FastAPI(
        title="filamind-iot-proxy",
        description=(
            "Self-hosted IoT-Box pairing rendezvous + ACME cert issuer. "
            "LGPL-3 alternative to iot-proxy.odoo.com."
        ),
        version="0.1.0",
        lifespan=lifespan,
    )
    app.include_router(health.router)
    app.include_router(pairing.router)
    app.include_router(admin.router)
    return app


app = create_app()
