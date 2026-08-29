from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from app.auth import get_current_user, get_effective_tenant_id, require_tenant
from app.schemas import ResourceCreate
from app.store import store

router = APIRouter(prefix="/resources", tags=["resources"])


@router.get("")
def list_resources(
    user: Annotated[dict, Depends(get_current_user)],
    tenant_id: Annotated[str | None, Depends(get_effective_tenant_id)],
):
    if user["role"] == "platform_admin" and not tenant_id:
        return store.scope(None, "resources")
    if not tenant_id:
        raise HTTPException(status_code=400, detail="Select a tenant")
    return store.scope(tenant_id, "resources")


@router.post("")
def create_resource(
    body: ResourceCreate,
    user: Annotated[dict, Depends(get_current_user)],
    tenant_id: Annotated[str, Depends(require_tenant)],
):
    return store.add_resource(tenant_id, body.model_dump())
