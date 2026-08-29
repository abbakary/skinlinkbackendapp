from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from app.auth import get_current_user, get_effective_tenant_id, require_tenant
from app.schemas import PatientCreate, PatientUpdate
from app.store import store

router = APIRouter(prefix="/patients", tags=["patients"])


@router.get("")
def list_patients(
    user: Annotated[dict, Depends(get_current_user)],
    tenant_id: Annotated[str | None, Depends(get_effective_tenant_id)],
):
    if user["role"] == "platform_admin" and not tenant_id:
        return store.scope(None, "patients")
    if not tenant_id:
        raise HTTPException(status_code=400, detail="Select a tenant")
    return store.scope(tenant_id, "patients")


@router.get("/{patient_id}")
def get_patient(
    patient_id: str,
    user: Annotated[dict, Depends(get_current_user)],
    tenant_id: Annotated[str | None, Depends(get_effective_tenant_id)],
):
    if user["role"] == "platform_admin" and not tenant_id:
        all_patients = store.scope(None, "patients")
    else:
        if not tenant_id:
            raise HTTPException(status_code=400, detail="Select a tenant")
        all_patients = store.scope(tenant_id, "patients")
    patient = next((p for p in all_patients if p["id"] == patient_id), None)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    return patient


@router.post("")
def create_patient(body: PatientCreate, user: Annotated[dict, Depends(get_current_user)], tenant_id: Annotated[str, Depends(require_tenant)]):
    tenant = store.get_tenant(tenant_id)
    data = body.model_dump()
    data["region"] = data.get("region") or (tenant["region"] if tenant else "Mwanza")
    return store.add_patient(tenant_id, data, user["id"])


@router.patch("/{patient_id}")
def update_patient(patient_id: str, body: PatientUpdate, user: Annotated[dict, Depends(get_current_user)]):
    patch = {k: v for k, v in body.model_dump().items() if v is not None}
    updated = store.update_patient(patient_id, patch)
    if not updated:
        raise HTTPException(status_code=404, detail="Patient not found")
    return updated
