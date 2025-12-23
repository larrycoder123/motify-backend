"""
Motify Backend API

FastAPI application providing REST endpoints for the Motify accountability platform.
Handles OAuth integration, user statistics, and background job triggers for
processing challenges on the Base L2 blockchain.

Deployment:
- API Server: Render (https://motify-backend-3k55.onrender.com)
- Scheduled Jobs: GitHub Actions (process-ready.yml)
"""

import logging
import traceback

from fastapi import FastAPI, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes_health import router as health_router
from app.api.routes_oauth import router as oauth_router
from app.api.routes_stats import router as stats_router
from app.core.config import settings
from app.services import chain_writer, indexer
from app.services.chain_reader import ChainReader

# =============================================================================
# CORS Configuration
# =============================================================================

ALLOWED_ORIGINS = [
    # Local development
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:5173",
    "http://localhost:8080",
    "http://127.0.0.1:8080",
    # Vercel previews
    "https://motify-nine.vercel.app",
    # Production
    "https://motify.live",
    "https://www.motify.live",
]


# =============================================================================
# Application Factory
# =============================================================================

def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="Motify API",
        description="Backend API for the Motify accountability platform on Base L2",
        version="1.0.0",
    )

    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=ALLOWED_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["*"],
    )

    @app.middleware("http")
    async def add_cors_headers(request, call_next):
        """Fallback CORS handler for Vercel preview deployments."""
        response = await call_next(request)
        origin = request.headers.get("origin")
        if origin in ALLOWED_ORIGINS or (origin and origin.endswith(".vercel.app")):
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Access-Control-Allow-Credentials"] = "true"
            response.headers["Access-Control-Allow-Methods"] = "*"
            response.headers["Access-Control-Allow-Headers"] = "*"
        return response

    # Register routers
    app.include_router(health_router)
    app.include_router(stats_router)
    app.include_router(oauth_router)

    # =========================================================================
    # Background Job Endpoints (Protected by CRON_SECRET)
    # =========================================================================

    def _verify_cron_secret(provided: str | None) -> bool:
        """Verify the cron secret header matches the configured secret."""
        expected = (settings.CRON_SECRET or "").strip()
        if not expected:
            return True
        return (provided or "").strip() == expected

    @app.post("/jobs/index-and-cache")
    async def job_index_and_cache(
        x_cron_secret: str | None = Header(default=None, alias="x-cron-secret")
    ):
        """Index ended challenges from chain and cache participant details."""
        if not _verify_cron_secret(x_cron_secret):
            return JSONResponse(status_code=401, content={"ok": False, "error": "unauthorized"})
        try:
            out = indexer.fetch_and_cache_ended_challenges(
                limit=500, only_ready_to_end=True, exclude_finished=True
            )
            det = indexer.cache_details_for_ready(limit=200)
            return {"ok": True, "index": out, "details": det}
        except Exception as e:
            logging.error("job_index_and_cache error: %s", e)
            return JSONResponse(status_code=500, content={"ok": False, "error": str(e)})

    @app.get("/jobs/debug-config")
    async def job_debug_config(
        x_cron_secret: str | None = Header(default=None, alias="x-cron-secret")
    ):
        """Debug endpoint to verify environment configuration."""
        if not _verify_cron_secret(x_cron_secret):
            return JSONResponse(status_code=401, content={"ok": False, "error": "unauthorized"})
        import os
        send_flag = os.getenv("SEND_TX") or os.getenv("TX_SEND") or "false"
        send_eval = str(send_flag).lower() in {"1", "true", "yes"}
        return {
            "ok": True,
            "env": {
                "SEND_TX": os.getenv("SEND_TX"),
                "TX_SEND": os.getenv("TX_SEND"),
            },
            "send_eval": send_eval,
            "default_percent_ppm": settings.DEFAULT_PERCENT_PPM,
        }

    @app.post("/jobs/declare-preview/{challenge_id}")
    async def job_declare_preview(
        challenge_id: int,
        x_cron_secret: str | None = Header(default=None, alias="x-cron-secret"),
        include_items: bool = False,
    ):
        """
        Preview declare payload for a challenge without sending transactions.
        
        Useful for debugging and verifying computed refund percentages before
        actually submitting on-chain.
        """
        if not _verify_cron_secret(x_cron_secret):
            return JSONResponse(status_code=401, content={"ok": False, "error": "unauthorized"})
        try:
            preview = indexer.prepare_run(
                challenge_id, default_percent_ppm=settings.DEFAULT_PERCENT_PPM
            )
            items = list(preview.get("items") or [])

            # Filter to only pending participants (not yet declared on-chain)
            pending_addrs_lc: set[str] = set()
            reader = ChainReader.from_settings()
            if reader is not None:
                detail = reader.get_challenge_detail(challenge_id)
                for p in detail.get("participants") or []:
                    if not p.get("result_declared"):
                        pending_addrs_lc.add(str(p.get("participant_address")).lower())
            if pending_addrs_lc:
                items = [it for it in items if str(it.get("user")).lower() in pending_addrs_lc]

            # Build payload without sending
            dec = {"dry_run": True, "payload": {"challenge_id": challenge_id, "chunks": []}, "tx_hashes": []}
            if items:
                dec = chain_writer.declare_results(challenge_id, items, chunk_size=200, send=False)
            
            resp = {"ok": True, "challenge_id": challenge_id, "items": len(items), "declare": dec}
            if include_items:
                resp["items_detail"] = [
                    {
                        "user": it.get("user"),
                        "stake_minor_units": it.get("stake_minor_units"),
                        "percent_ppm": it.get("percent_ppm"),
                        "progress_ratio": it.get("progress_ratio"),
                    }
                    for it in items
                ]
            return resp
        except Exception as e:
            logging.error("job_declare_preview error: %s", e)
            return JSONResponse(status_code=500, content={"ok": False, "error": str(e)})

    # =========================================================================
    # Global Exception Handler
    # =========================================================================

    @app.exception_handler(Exception)
    async def generic_exception_handler(request, exc: Exception):
        """Catch-all handler to prevent exposing internal errors to clients."""
        logging.error("Unhandled exception: %s", exc)
        logging.error("Traceback:\n%s", "".join(
            traceback.format_exception(type(exc), exc, exc.__traceback__)
        ))
        
        response = JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "INTERNAL",
                    "message": "Unexpected error",
                    "details": {"type": exc.__class__.__name__},
                }
            },
        )
        
        # Add CORS headers to error responses for allowed origins
        origin = request.headers.get("origin", "")
        if origin in ALLOWED_ORIGINS or "vercel.app" in origin or "localhost" in origin:
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Access-Control-Allow-Credentials"] = "true"
        
        return response

    return app


# =============================================================================
# Application Instance
# =============================================================================

app = create_app()
