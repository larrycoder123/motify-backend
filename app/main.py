from fastapi import FastAPI
from fastapi.responses import JSONResponse

from app.api.routes_health import router as health_router
from app.api.routes_webhooks import router as webhooks_router
from app.api.routes_challenges import router as challenges_router
from app.api.routes_users import router as users_router
from app.api.routes_integrations import router as integrations_router
from app.api.routes_leaderboards import router as leaderboards_router


def create_app() -> FastAPI:
    app = FastAPI(title="Motify API", version="0.1.0")

    # Routers
    app.include_router(health_router)
    app.include_router(webhooks_router)
    app.include_router(challenges_router)
    app.include_router(users_router)
    app.include_router(integrations_router)
    app.include_router(leaderboards_router)

    @app.exception_handler(Exception)
    async def generic_exception_handler(_, exc: Exception):
        # Uniform error envelope
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
