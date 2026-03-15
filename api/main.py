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


@app.get("/health")
def health():
    return {"status": "ok"}
