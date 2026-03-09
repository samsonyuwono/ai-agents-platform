#!/usr/bin/env bash
# Start the Reservation Agent web API for local development
cd "$(dirname "$0")/.." || exit 1
uvicorn api.main:app --reload --port 8000
