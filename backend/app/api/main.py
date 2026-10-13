"""FastAPI application. Run from backend/:  uvicorn app.api:app --port 8000

Nothing here calls Groq or apna.co unless a logged-in user starts a search.
"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from .. import config
from ..sources import refresher
from . import routes_auth, routes_data, routes_search, routes_voice


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(refresher.loop(config.AUTO_REFRESH_MINUTES)) if config.AUTO_REFRESH_MINUTES > 0 else None
    yield
    if task:
        task.cancel()


app = FastAPI(title="WorkWeave: agentic job search", lifespan=lifespan)
# Only the short Google handshake uses this cookie; the login session is our own (see accounts.store).
app.add_middleware(SessionMiddleware, secret_key=config.SECRET_KEY, session_cookie="oauth_flow", max_age=600, same_site="lax",
                   https_only=config.COOKIE_SECURE)
for router in (routes_auth.router, routes_search.router, routes_data.router, routes_voice.router):
    app.include_router(router)

if config.FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=config.FRONTEND_DIR), name="static")

    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(config.FRONTEND_DIR / "index.html")
