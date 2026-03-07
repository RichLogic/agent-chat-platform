"""FastAPI application entry point."""

from __future__ import annotations

from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from agent_chat.config import Settings, set_settings
from agent_chat.db.mongo import connect_db, disconnect_db, create_indexes
from agent_chat.api.router import api_router

import structlog
from structlog._log_levels import NAME_TO_LEVEL

setup_done = False


def setup_logging(level: str) -> None:
    global setup_done
    if setup_done:
        return
    setup_done = True
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            NAME_TO_LEVEL[level.lower()]
        ),
    )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application lifespan: initialize and cleanup resources."""
    settings = Settings()
    set_settings(settings)
    setup_logging(settings.log_level)

    logger = structlog.get_logger()
    logger.info("starting_up", mongo_uri=settings.mongo_uri, db=settings.mongo_db)

    # MongoDB
    db = await connect_db(settings.mongo_uri, settings.mongo_db)
    await create_indexes(db)

    # Clean up zombie runs left by previous crashes/restarts
    from agent_chat.db.repository import cleanup_zombie_runs
    zombies = await cleanup_zombie_runs()
    if zombies:
        logger.warning("zombie_runs_cleaned", count=zombies)

    yield

    # Cleanup
    await disconnect_db()
    logger.info("shut_down")


def create_app() -> FastAPI:
    settings = Settings()

    app = FastAPI(
        title="Agent Chat Platform",
        description="AI Agent Chat Platform with streaming support",
        version="0.1.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(api_router)

    return app


app = create_app()
