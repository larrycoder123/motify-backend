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
from app.services.chain_reader import ChainReader
from app.services import chain_writer


def create_app() -> FastAPI:
    app = FastAPI(title="Motify API", version="0.1.0")

    # CORS for local dev and preview origins
    # Add wildcard for Vercel preview deployments
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:3000",
            "http://127.0.0.1:3000",
            "http://localhost:5173",
            "http://localhost:8080",
            "http://127.0.0.1:8080",
            "https://motify-nine.vercel.app",
            # Note: Starlette doesn't support wildcard entries here; use allow_origin_regex or manual middleware below
            # "https://*.vercel.app",  # handled by manual middleware below
            # Production frontend domains
            "https://motify.live",
            "https://www.motify.live",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["*"],  # Add this
    )

    # Add a middleware to manually add CORS headers as a fallback
    @app.middleware("http")
    async def add_cors_headers(request, call_next):
        response = await call_next(request)
        origin = request.headers.get("origin")
        allowed_origins = [
            "http://localhost:3000",
            "http://127.0.0.1:3000",
            "http://localhost:5173",
            "http://localhost:8080",
            "http://127.0.0.1:8080",
            # Production frontend domains
            "https://motify.live",
            "https://www.motify.live",
        ]
        
        if origin in allowed_origins or (origin and origin.endswith(".vercel.app")):
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Access-Control-Allow-Credentials"] = "true"
            response.headers["Access-Control-Allow-Methods"] = "*"
            response.headers["Access-Control-Allow-Headers"] = "*"
        
        return response

    # Routers
    app.include_router(health_router)
    app.include_router(stats_router)
    app.include_router(oauth_router)

    @app.post("/jobs/index-and-cache")
    async def job_index_and_cache(x_cron_secret: str | None = Header(default=None, alias="x-cron-secret")):
        expected = (settings.CRON_SECRET or "").strip()
        if expected:
            provided = (x_cron_secret or "").strip()
            if provided != expected:
                return JSONResponse(status_code=401, content={"ok": False, "error": "unauthorized"})
        try:
            out = indexer.fetch_and_cache_ended_challenges(
                limit=500, only_ready_to_end=True, exclude_finished=True)
            det = indexer.cache_details_for_ready(limit=200)
            return {"ok": True, "index": out, "details": det}
        except Exception as e:
            logging.error("job_index_and_cache error: %s", e)
            return JSONResponse(status_code=500, content={"ok": False, "error": str(e)})

    @app.get("/jobs/debug-config")
    async def job_debug_config(x_cron_secret: str | None = Header(default=None, alias="x-cron-secret")):
        expected = (settings.CRON_SECRET or "").strip()
        if expected:
            if (x_cron_secret or "").strip() != expected:
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
    async def job_declare_preview(challenge_id: int, x_cron_secret: str | None = Header(default=None, alias="x-cron-secret"), include_items: bool = False):
        """Build declare payload for a challenge without sending transactions.

        This previews the exact chunks and ppm values that would be used.
        Protected with x-cron-secret.
        """
        expected = (settings.CRON_SECRET or "").strip()
        if expected:
            if (x_cron_secret or "").strip() != expected:
                return JSONResponse(status_code=401, content={"ok": False, "error": "unauthorized"})
        try:
            # Prepare items as the processor does
            preview = indexer.prepare_run(challenge_id, default_percent_ppm=settings.DEFAULT_PERCENT_PPM)
            items = list(preview.get("items") or [])

            # Restrict to pending participants by reading on-chain state
            pending_addrs_lc: set[str] = set()
            reader = ChainReader.from_settings()
            if reader is not None:
                detail = reader.get_challenge_detail(challenge_id)
                for p in (detail.get("participants") or []):
                    if not p.get("result_declared"):
                        pending_addrs_lc.add(str(p.get("participant_address")).lower())
            if pending_addrs_lc:
                items = [it for it in items if str(it.get("user")).lower() in pending_addrs_lc]

            # Build declare payload without sending
            dec = {"dry_run": True, "payload": {"challenge_id": challenge_id, "chunks": []}, "tx_hashes": []}
            if items:
                dec = chain_writer.declare_results(challenge_id, items, chunk_size=200, send=False)
            resp = {"ok": True, "challenge_id": challenge_id, "items": len(items), "declare": dec}
            if include_items:
                # include trimmed details to expose progress vs fallback
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

    @app.exception_handler(Exception)
    async def generic_exception_handler(request, exc: Exception):
        logging.error("Unhandled exception: %s", exc)
        logging.error("Traceback:\n%s", ''.join(
            traceback.format_exception(type(exc), exc, exc.__traceback__)))
        
        # Create response with CORS headers
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
        
        # Manually add CORS headers to error responses
        origin = request.headers.get("origin", "")
        if "vercel.app" in origin or "localhost" in origin:
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Access-Control-Allow-Credentials"] = "true"
        
        return response

    return app


app = create_app()
