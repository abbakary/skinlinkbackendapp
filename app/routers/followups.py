from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from app.auth import get_current_user, get_effective_tenant_id, require_tenant
from app.schemas import FollowUpCreate, FollowUpUpdate
from app.store import store

router = APIRouter(prefix="/follow-ups", tags=["follow-ups"])


@router.get("")
def list_follow_ups(
    user: Annotated[dict, Depends(get_current_user)],
    tenant_id: Annotated[str | None, Depends(get_effective_tenant_id)],
):
    if user["role"] == "platform_admin" and not tenant_id:
        return store.scope(None, "followUps")
    if not tenant_id:
        raise HTTPException(status_code=400, detail="Select a tenant")
    return store.scope(tenant_id, "followUps")


@router.patch("/{follow_up_id}")
def update_follow_up(follow_up_id: str, body: FollowUpUpdate, user: Annotated[dict, Depends(get_current_user)]):
    patch = {k: v for k, v in body.model_dump().items() if v is not None}
    updated = store.update_follow_up(follow_up_id, patch)
    if not updated:
        raise HTTPException(status_code=404, detail="Follow-up not found")
    if patch.get("followUpReport") and updated.get("caseId"):
        case = next((c for c in store.db.get("cases", []) if c["id"] == updated["caseId"]), None)
        if case:
            existing_report = case.get("followUpReport", {})
            merged = {**existing_report, **patch["followUpReport"]}
            spec_action = patch["followUpReport"].get("specialistAction")
            new_case_status = "closed" if spec_action == "discharge" else ("reviewed" if spec_action else "follow_up")
            store.update_case(updated["caseId"], {
                "followUpReport": merged,
                "status": new_case_status,
            })
    return updated


@router.post("")
def create_follow_up(body: FollowUpCreate, user: Annotated[dict, Depends(get_current_user)], tenant_id: Annotated[str, Depends(require_tenant)]):
    return store.add_follow_up(tenant_id, body.model_dump())
