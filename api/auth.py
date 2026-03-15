"""Authentication: login endpoint and Bearer token dependency."""

import time
from dataclasses import dataclass
from typing import Optional

import jwt
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from config.settings import Settings
from api.schemas import LoginRequest, LoginResponse

router = APIRouter(prefix="/api/auth", tags=["auth"])
security = HTTPBearer()

JWT_ALGORITHM = "HS256"
JWT_EXPIRY_SECONDS = 60 * 60 * 24 * 7  # 7 days


@dataclass
class AuthUser:
    """Authenticated user extracted from JWT."""
    sub: str
    resy_email: Optional[str] = None


def _create_token(resy_email: Optional[str] = None) -> str:
    payload = {
        "sub": "user",
        "iat": int(time.time()),
        "exp": int(time.time()) + JWT_EXPIRY_SECONDS,
    }
    if resy_email:
        payload["resy_email"] = resy_email
    return jwt.encode(payload, Settings.WEB_JWT_SECRET, algorithm=JWT_ALGORITHM)


def require_auth(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> AuthUser:
    """FastAPI dependency that validates the Bearer token."""
    token = credentials.credentials
    try:
        payload = jwt.decode(
            token, Settings.WEB_JWT_SECRET, algorithms=[JWT_ALGORITHM]
        )
        return AuthUser(
            sub=payload["sub"],
            resy_email=payload.get("resy_email"),
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")


@router.post("/login", response_model=LoginResponse)
def login(body: LoginRequest):
    """Validate password and return a JWT."""
    if not Settings.WEB_AUTH_PASSWORD:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="WEB_AUTH_PASSWORD not configured on server",
        )
    if body.password != Settings.WEB_AUTH_PASSWORD:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid password"
        )
    return LoginResponse(token=_create_token())
