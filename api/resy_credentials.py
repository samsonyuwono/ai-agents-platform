"""Resy credential linking: link, status, and unlink endpoints."""

import logging

from fastapi import APIRouter, Depends, HTTPException, status

from api.auth import require_auth, AuthUser, _create_token
from api.schemas import ResyLinkRequest, ResyLinkResponse, ResyStatusResponse
from config.settings import Settings
from utils.credential_store import CredentialStore
from utils.resy_client import ResyClient

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/resy", tags=["resy"])


def _get_credential_store() -> CredentialStore:
    """Return a CredentialStore instance (allows test overriding)."""
    return CredentialStore()


@router.post("/link", response_model=ResyLinkResponse)
def link_resy(
    body: ResyLinkRequest,
    user: AuthUser = Depends(require_auth),
):
    """Validate Resy credentials and store them encrypted."""
    # Validate against Resy's auth endpoint
    client = ResyClient(api_key=Settings.RESY_API_KEY or Settings.RESY_PUBLIC_API_KEY)
    try:
        auth_token = client.refresh_auth_token(body.email, body.password)
    except Exception as e:
        logger.warning("Resy auth failed for %s: %s", body.email, e)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Resy credentials",
        )

    # Store encrypted credentials
    with _get_credential_store() as store:
        store.save_credentials(body.email, body.password, auth_token=auth_token)

    # Re-issue JWT with resy_email claim
    new_token = _create_token(resy_email=body.email)

    return ResyLinkResponse(success=True, token=new_token, resy_email=body.email)


@router.get("/status", response_model=ResyStatusResponse)
def resy_status(user: AuthUser = Depends(require_auth)):
    """Check if the current user has linked Resy credentials."""
    if not user.resy_email:
        return ResyStatusResponse(linked=False)

    with _get_credential_store() as store:
        linked = store.has_credentials(user.resy_email)

    return ResyStatusResponse(linked=linked, resy_email=user.resy_email if linked else None)


@router.delete("/unlink")
def unlink_resy(user: AuthUser = Depends(require_auth)):
    """Delete stored Resy credentials and re-issue JWT without resy_email."""
    if user.resy_email:
        with _get_credential_store() as store:
            store.delete_credentials(user.resy_email)

    new_token = _create_token()  # No resy_email
    return {"success": True, "token": new_token}
