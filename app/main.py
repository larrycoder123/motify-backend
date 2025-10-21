from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import logging
import traceback

from app.api.routes_health import router as health_router
from app.api.routes_stats import router as stats_router
from app.api.routes_oauth import router as oauth_router
from app.core.config import settings
from app.services import indexer
from fastapi import Header


def create_app() -> FastAPI:
    app = FastAPI(title="Motify API", version="0.1.0")

    # CORS for local dev and preview origins
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:3000",
            "http://127.0.0.1:3000",
            "http://localhost:5173",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Routers
    app.include_router(health_router)
    app.include_router(stats_router)
    app.include_router(oauth_router)
    # Indexer and chain reader endpoints removed; use internal services/CLI instead.

    # Optional: tiny index-only job endpoint for Vercel Cron (guarded by header)
    @app.post("/jobs/index-and-cache")
    async def job_index_and_cache(x_cron_secret: str | None = Header(default=None, alias="x-cron-secret")):
        # Protect with simple shared secret header when deployed on Vercel Cron
        # Client must send header: x-cron-secret: <CRON_SECRET>
        from fastapi import Request
        # Use dependency injection to access headers
        # Workaround: Accept param and fallback to reading from global context isn't ideal in FastAPI
        # so we'll read directly from starlette Request via kwargs capture
        # but here, for simplicity, expect frameworks to map header -> x_cron_secret
        expected = (settings.CRON_SECRET or "").strip()
        if expected:
            provided = (x_cron_secret or "").strip()
            if provided != expected:
                return JSONResponse(status_code=401, content={"ok": False, "error": "unauthorized"})
        try:
            out = indexer.fetch_and_cache_ended_challenges(
                limit=500, only_ready_to_end=True, exclude_finished=True)
            # Also ensure participants for ready challenges
            det = indexer.cache_details_for_ready(limit=200)
            return {"ok": True, "index": out, "details": det}
        except Exception as e:
            logging.error("job_index_and_cache error: %s", e)
            return JSONResponse(status_code=500, content={"ok": False, "error": str(e)})

    @app.exception_handler(Exception)
    async def generic_exception_handler(_, exc: Exception):
        # Uniform error envelope
        logging.error("Unhandled exception: %s", exc)
        logging.error("Traceback:\n%s", ''.join(
            traceback.format_exception(type(exc), exc, exc.__traceback__)))
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "INTERNAL",
                    "message": "Unexpected error",
                    "details": {"type": exc.__class__.__name__},
                }
            },
        )

    return app


app = create_app()
