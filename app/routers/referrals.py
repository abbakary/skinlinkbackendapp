from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from app.auth import get_current_user, get_effective_tenant_id
from app.schemas import ReferralUpdate
from app.store import store

router = APIRouter(prefix="/referrals", tags=["referrals"])


@router.get("")
def list_referrals(
    user: Annotated[dict, Depends(get_current_user)],
    tenant_id: Annotated[str | None, Depends(get_effective_tenant_id)],
):
    if user["role"] == "platform_admin" and not tenant_id:
        return store.scope(None, "referrals")
    if not tenant_id:
        raise HTTPException(status_code=400, detail="Select a tenant")
    return store.scope(tenant_id, "referrals")


@router.patch("/{referral_id}")
def update_referral(referral_id: str, body: ReferralUpdate, user: Annotated[dict, Depends(get_current_user)]):
    patch = {k: v for k, v in body.model_dump().items() if v is not None}
    if patch.get("status") == "responded" and "respondedAt" not in patch:
        from datetime import datetime, timezone
        patch["respondedAt"] = datetime.now(timezone.utc).isoformat()
    updated = store.update_referral(referral_id, patch)
    if not updated:
        raise HTTPException(status_code=404, detail="Referral not found")
    return updated
