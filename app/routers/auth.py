from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Header, HTTPException

from app.auth import create_access_token, get_current_user
from app.schemas import LoginRequest, TokenResponse
from app.store import store

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
def login(
    body: LoginRequest,
    x_client_platform: Annotated[Optional[str], Header()] = None,
):
    user = store.get_user_by_email(body.email)
    if not user or not store.verify_password(body.email, body.password):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if user.get("status") == "disabled":
        raise HTTPException(status_code=403, detail="Account disabled")
    if x_client_platform == "web" and user.get("role") == "clinician":
        raise HTTPException(
            status_code=403,
            detail="Clinician & Nurse accounts are restricted to the SkinLink Mobile App. Please sign in via the mobile application."
        )
    tenant = store.get_tenant(user["tenantId"]) if user.get("tenantId") else None
    token = create_access_token(user["id"], user.get("tenantId"))
    return TokenResponse(
        access_token=token,
        user=user,
        tenant=tenant,
    )


@router.get("/me")
def me(user: Annotated[dict, Depends(get_current_user)]):
    tenant = store.get_tenant(user["tenantId"]) if user.get("tenantId") else None
    return {"user": user, "tenant": tenant}
