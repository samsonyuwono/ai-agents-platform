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


class ResyLinkRequest(BaseModel):
    email: str
    password: str


class ResyLinkResponse(BaseModel):
    success: bool
    token: str
    resy_email: str


class ResyStatusResponse(BaseModel):
    linked: bool
    resy_email: Optional[str] = None
