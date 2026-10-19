"""Application entrypoint."""

import os
import sys
from contextlib import asynccontextmanager

# Running this file directly (`python app/main.py`) puts app/ on sys.path
# rather than the project root, so "from app.config import ..." would fail
# with ModuleNotFoundError. Adding the project root makes the entrypoint
# work whether it is run as a script or as a module (`python -m app.main`),
# and both are used: the sandbox's server probe invokes it directly.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.errors import register_exception_handlers

# Importing the router also imports app.models.user, which registers the
# User table on Base.metadata so init_db() creates it at startup.
from app.routers.users import router as users_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: create the real schema so the app is usable on first boot.
    # A connectivity-only check here would leave every query failing
    # against a database with no tables.
    from app.db import init_db

    await init_db()
    yield


def create_app() -> FastAPI:
    app = FastAPI(title=settings.app_name, lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Global exception handlers (port of the Spring @ControllerAdvice),
    # including the catch-all Exception handler.
    register_exception_handlers(app)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(users_router)

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    # 0.0.0.0, not localhost — the app runs in a container and must be
    # reachable from outside it.
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8000")))