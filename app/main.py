from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import logging
import traceback

from app.api.routes_health import router as health_router
from app.api.routes_webhooks import router as webhooks_router
from app.api.routes_challenges import router as challenges_router
from app.api.routes_users import router as users_router
from app.api.routes_integrations import router as integrations_router
from app.api.routes_leaderboards import router as leaderboards_router
from app.api.routes_chain import router as chain_router
from app.core.config import settings
import logging
from app.services.chain_handlers import handle_challenge_created_event
import threading
import time


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
    app.include_router(webhooks_router)
    app.include_router(challenges_router)
    app.include_router(users_router)
    app.include_router(integrations_router)
    app.include_router(leaderboards_router)
    app.include_router(chain_router)

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

    # Optional: start a lightweight background poller (placeholder for a chain listener)
    if settings.ENABLE_CHAIN_LISTENER:
        def _poller():
            try:
                from app.services.web3client import Web3Listener, ListenerConfig
                from app.models.db import SupabaseDAL
                dal = SupabaseDAL.from_env()
                if not (settings.WEB3_RPC_URL and settings.MOTIFY_CONTRACT_ADDRESS and settings.MOTIFY_CONTRACT_ABI_PATH):
                    logging.warning("Chain listener enabled but WEB3 env not fully configured; skipping start")
                    return
                cfg = ListenerConfig(
                    rpc_url=settings.WEB3_RPC_URL,
                    contract_address=settings.MOTIFY_CONTRACT_ADDRESS,
                    abi_path=settings.MOTIFY_CONTRACT_ABI_PATH,
                    confirmations=int(settings.CHAIN_CONFIRMATIONS),
                    poll_seconds=float(settings.CHAIN_POLL_SECONDS),
                )
                logging.info("[chain] starting listener on %s for %s", settings.WEB3_RPC_URL, settings.MOTIFY_CONTRACT_ADDRESS)
                listener = Web3Listener(cfg)
                def _handle(event: dict):
                    if not dal:
                        return
                    # Attempt to attach by id first; fall back to contract-only match
                    try:
                        logging.info("[chain] ChallengeCreated id=%s creator=%s", event.get("challenge_id"), event.get("creator"))
                        handle_challenge_created_event(
                            dal,
                            contract_address=settings.MOTIFY_CONTRACT_ADDRESS,
                            on_chain_challenge_id=int(event.get("challenge_id")),
                            owner_wallet=(event.get("creator") or None),
                            description_hash=(event.get("metadata_hash") or None),
                            created_tx_hash=(event.get("transactionHash") or None),
                            created_block_number=(event.get("blockNumber") or None),
                        )
                        logging.info("[chain] attached id=%s to challenge row", event.get("challenge_id"))
                    except Exception:
                        # swallow to keep listener alive; logs are emitted in handler
                        logging.exception("[chain] handler failed for event: %s", event)
                from app.services.chain_handlers import handle_joined_challenge_event
                def _handle_joined(evt: dict):
                    if not dal:
                        return
                    try:
                        logging.info("[chain] JoinedChallenge id=%s user=%s amount=%s", evt.get("challenge_id"), evt.get("user"), evt.get("amount"))
                        handle_joined_challenge_event(
                            dal,
                            contract_address=settings.MOTIFY_CONTRACT_ADDRESS,
                            on_chain_challenge_id=int(evt.get("challenge_id")),
                            user_wallet=str(evt.get("user") or ""),
                            amount_minor_units=int(evt.get("amount") or 0),
                            tx_hash=(evt.get("transactionHash") or None),
                            block_number=(evt.get("blockNumber") or None),
                        )
                    except Exception:
                        logging.exception("[chain] handler failed for JoinedChallenge: %s", evt)

                listener.poll_loop(_handle, _handle_joined)
            except Exception:
                # Never crash the app if listener fails to start
                logging.exception("[chain] listener failed to start")
        threading.Thread(target=_poller, daemon=True).start()

    return app


app = create_app()
