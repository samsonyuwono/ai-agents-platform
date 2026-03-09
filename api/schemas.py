"""Pydantic models for the chat API."""

from typing import Optional
from pydantic import BaseModel


class LoginRequest(BaseModel):
    password: str


class LoginResponse(BaseModel):
    token: str


class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None
