"""FastAPI application — entry point for the Reservation Agent web API."""

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config.settings import Settings
from api.auth import router as auth_router
from api.chat import router as chat_router
from api.resy_credentials import router as resy_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

app = FastAPI(title="Reservation Agent API", version="1.0.0")

# CORS — allow the frontend origin(s)
origins = [o.strip() for o in Settings.WEB_CORS_ORIGINS.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(chat_router)
app.include_router(resy_router)


@app.on_event("startup")
async def _prewarm_browser_worker():
    """Pre-warm the browser worker in a background thread so first request is fast."""
    import threading

    def _warm():
        try:
            if not Settings.has_resy_browser_configured():
                return
            from utils.browser_worker_manager import BrowserWorkerManager
            manager = BrowserWorkerManager.get_instance()
            result = manager.send_command("ping", {}, timeout=Settings.RESY_BROWSER_WORKER_STARTUP_TIMEOUT)
            logging.getLogger(__name__).info("Browser worker pre-warm: %s", result.get("status", result))
        except Exception as e:
            logging.getLogger(__name__).warning("Browser worker pre-warm failed (non-fatal): %s", e)

    threading.Thread(target=_warm, daemon=True).start()


@app.on_event("shutdown")
async def _shutdown_browser_worker():
    """Gracefully shut down the browser worker on app shutdown."""
    try:
        from utils.browser_worker_manager import BrowserWorkerManager
        BrowserWorkerManager.get_instance().shutdown()
    except Exception:
        pass


@app.get("/health")
def health():
    return {"status": "ok"}
