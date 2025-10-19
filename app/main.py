from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import logging
import traceback

from app.api.routes_health import router as health_router


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
    # Indexer and chain reader endpoints removed; use internal services/CLI instead.

    @app.exception_handler(Exception)
    async def generic_exception_handler(_, exc: Exception):
        # Uniform error envelope
        logging.error("Unhandled exception: %s", exc)
        logging.error("Traceback:\n%s", ''.join(traceback.format_exception(type(exc), exc, exc.__traceback__)))
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
