.PHONY: start-reservation-api

start-reservation-api:
	uvicorn api.main:app --reload --port 8000
