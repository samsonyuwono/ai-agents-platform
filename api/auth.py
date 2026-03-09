"""Authentication: login endpoint and Bearer token dependency."""

import time

import jwt
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from config.settings import Settings
from api.schemas import LoginRequest, LoginResponse

router = APIRouter(prefix="/api/auth", tags=["auth"])
security = HTTPBearer()

JWT_ALGORITHM = "HS256"
JWT_EXPIRY_SECONDS = 60 * 60 * 24 * 7  # 7 days


def _create_token() -> str:
    payload = {
        "sub": "user",
        "iat": int(time.time()),
        "exp": int(time.time()) + JWT_EXPIRY_SECONDS,
    }
    return jwt.encode(payload, Settings.WEB_JWT_SECRET, algorithm=JWT_ALGORITHM)


def require_auth(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> str:
    """FastAPI dependency that validates the Bearer token."""
    token = credentials.credentials
    try:
        payload = jwt.decode(
            token, Settings.WEB_JWT_SECRET, algorithms=[JWT_ALGORITHM]
        )
        return payload["sub"]
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
