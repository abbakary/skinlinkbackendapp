from datetime import datetime, timezone
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException

from app.auth import get_current_user, get_effective_tenant_id, require_platform_admin
from app.schemas import TenantCreate, TenantUpdate, UserCreate, UserUpdate, UserPasswordReset
from app.store import store

router = APIRouter(tags=["admin"])


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@router.get("/tenants")
def list_tenants(user: Annotated[dict, Depends(get_current_user)]):
    if user["role"] == "platform_admin":
        return store.scope(None, "tenants")
    tenant_id = user.get("tenantId")
    if not tenant_id:
        raise HTTPException(status_code=400, detail="No organization")
    tenant = store.get_tenant(tenant_id)
    return [tenant] if tenant else []


@router.post("/tenants")
def create_tenant(body: TenantCreate, _: Annotated[dict, Depends(require_platform_admin)]):
    existing = store.get_user_by_email(body.adminEmail)
    if existing:
        raise HTTPException(status_code=400, detail="Admin email already in use")
    tenant, admin = store.create_tenant_account(body.model_dump())
    return {"tenant": tenant, "admin": admin}


@router.patch("/tenants/{tenant_id}")
def update_tenant(
    tenant_id: str,
    body: TenantUpdate,
    user: Annotated[dict, Depends(get_current_user)],
):
    if user["role"] != "platform_admin" and user.get("tenantId") != tenant_id:
        raise HTTPException(status_code=403, detail="Not allowed")
    patch = {k: v for k, v in body.model_dump().items() if v is not None}
    updated = store.update_tenant(tenant_id, patch)
    if not updated:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return updated


@router.get("/users")
def list_users(
    user: Annotated[dict, Depends(get_current_user)],
    tenant_id: Annotated[str | None, Depends(get_effective_tenant_id)],
):
    if user["role"] == "platform_admin" and not tenant_id:
        return store.list_users(None)
    if not tenant_id:
        raise HTTPException(status_code=400, detail="Select a tenant")
    return store.list_users(tenant_id)


@router.post("/users")
def create_user(body: UserCreate, user: Annotated[dict, Depends(get_current_user)]):
    if user["role"] not in ("platform_admin", "org_admin"):
        raise HTTPException(status_code=403, detail="Not allowed")
    if user["role"] == "org_admin" and user.get("tenantId") != body.tenantId:
        raise HTTPException(status_code=403, detail="Not allowed")
    if store.get_user_by_email(body.email):
        raise HTTPException(status_code=400, detail="Email already in use")
    return store.add_user(body.model_dump(exclude={"password"}), body.password)


@router.patch("/users/{user_id}")
def update_user(
    user_id: str,
    body: UserUpdate,
    user: Annotated[dict, Depends(get_current_user)],
):
    target = store.get_user(user_id)
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    if user["role"] == "org_admin" and user.get("tenantId") != target.get("tenantId"):
        raise HTTPException(status_code=403, detail="Not allowed")
    if user["role"] not in ("platform_admin", "org_admin") and user["id"] != user_id:
        raise HTTPException(status_code=403, detail="Not allowed")
    patch = {k: v for k, v in body.model_dump().items() if v is not None}
    updated = store.update_user(user_id, patch)
    if not updated:
        raise HTTPException(status_code=404, detail="User not found")
    return updated


@router.get("/tenants/{tenant_id}")
def get_tenant(
    tenant_id: str,
    user: Annotated[dict, Depends(get_current_user)],
):
    if user["role"] != "platform_admin" and user.get("tenantId") != tenant_id:
        raise HTTPException(status_code=403, detail="Not allowed")
    tenant = store.get_tenant(tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return tenant


@router.delete("/tenants/{tenant_id}", status_code=204)
def delete_tenant(
    tenant_id: str,
    _: Annotated[dict, Depends(require_platform_admin)],
):
    """Hard-delete a tenant and all its data (platform_admin only)."""
    tenant = store.get_tenant(tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    store.delete_tenant(tenant_id)


@router.delete("/users/{user_id}", status_code=204)
def delete_user(
    user_id: str,
    user: Annotated[dict, Depends(get_current_user)],
):
    if user["role"] not in ("platform_admin", "org_admin"):
        raise HTTPException(status_code=403, detail="Not allowed")
    target = store.get_user(user_id)
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    if user["role"] == "org_admin" and user.get("tenantId") != target.get("tenantId"):
        raise HTTPException(status_code=403, detail="Not allowed")
    if target.get("role") == "platform_admin":
        raise HTTPException(status_code=403, detail="Cannot delete a platform admin")
    store.delete_user(user_id)


@router.post("/users/{user_id}/reset-password", status_code=204)
def reset_user_password(
    user_id: str,
    body: UserPasswordReset,
    user: Annotated[dict, Depends(get_current_user)],
):
    """Allow org_admin or platform_admin to set a new password for any user in their tenant."""
    if user["role"] not in ("platform_admin", "org_admin"):
        raise HTTPException(status_code=403, detail="Not allowed")
    target = store.get_user(user_id)
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    if user["role"] == "org_admin" and user.get("tenantId") != target.get("tenantId"):
        raise HTTPException(status_code=403, detail="Not allowed")
    if target.get("role") == "platform_admin" and user["role"] != "platform_admin":
        raise HTTPException(status_code=403, detail="Cannot reset a platform admin password")
    if len(body.password) < 6:
        raise HTTPException(status_code=422, detail="Password must be at least 6 characters")
    store.set_password(target["email"], body.password)


@router.get("/stats/platform")
def platform_stats(_: Annotated[dict, Depends(require_platform_admin)]) -> dict[str, Any]:
    """BI summary across all tenants for the provider dashboard."""
    tenants = store.scope(None, "tenants")
    users = store.list_users(None)
    cases = store.scope(None, "cases")
    patients = store.scope(None, "patients")
    referrals = store.scope(None, "referrals")

    total_seats = sum(t.get("seats", 0) for t in tenants)
    used_seats = sum(t.get("usedSeats", 0) for t in tenants)

    # Cases by status across all tenants
    status_counts: dict[str, int] = {}
    for c in cases:
        s = c.get("status", "unknown")
        status_counts[s] = status_counts.get(s, 0) + 1

    # Cases by priority
    priority_counts: dict[str, int] = {}
    for c in cases:
        p = c.get("priority", "routine")
        priority_counts[p] = priority_counts.get(p, 0) + 1

    # Per-tenant breakdown
    tenant_breakdown = []
    for t in tenants:
        tid = t["id"]
        t_cases = [c for c in cases if c.get("tenantId") == tid]
        t_patients = [p for p in patients if p.get("tenantId") == tid]
        t_users = [u for u in users if u.get("tenantId") == tid]
        t_referrals = [r for r in referrals if r.get("tenantId") == tid]
        ai_cases = [c for c in t_cases if c.get("ai")]
        tenant_breakdown.append({
            "tenantId": tid,
            "name": t.get("name"),
            "plan": t.get("plan"),
            "status": t.get("status"),
            "region": t.get("region"),
            "country": t.get("country"),
            "seats": t.get("seats", 0),
            "usedSeats": t.get("usedSeats", 0),
            "seatUtilPct": round(t.get("usedSeats", 0) / t.get("seats", 1) * 100),
            "users": len(t_users),
            "patients": len(t_patients),
            "cases": len(t_cases),
            "referrals": len(t_referrals),
            "aiAssessments": len(ai_cases),
            "openCases": len([c for c in t_cases if c.get("status") in ("new", "in_review")]),
            "createdAt": t.get("createdAt"),
        })

    # Users by role
    role_counts: dict[str, int] = {}
    for u in users:
        if u.get("role") != "platform_admin":
            r = u.get("role", "unknown")
            role_counts[r] = role_counts.get(r, 0) + 1

    # Plan distribution
    plan_counts: dict[str, int] = {}
    for t in tenants:
        p = t.get("plan", "pilot")
        plan_counts[p] = plan_counts.get(p, 0) + 1

    # Status distribution
    tenant_status_counts: dict[str, int] = {}
    for t in tenants:
        s = t.get("status", "unknown")
        tenant_status_counts[s] = tenant_status_counts.get(s, 0) + 1

    return {
        "summary": {
            "totalTenants": len(tenants),
            "activeTenants": tenant_status_counts.get("active", 0),
            "trialTenants": tenant_status_counts.get("trial", 0),
            "suspendedTenants": tenant_status_counts.get("suspended", 0),
            "totalUsers": len([u for u in users if u.get("role") != "platform_admin"]),
            "totalPatients": len(patients),
            "totalCases": len(cases),
            "openCases": status_counts.get("new", 0) + status_counts.get("in_review", 0),
            "totalReferrals": len(referrals),
            "totalSeats": total_seats,
            "usedSeats": used_seats,
            "seatUtilPct": round(used_seats / total_seats * 100) if total_seats else 0,
        },
        "casesByStatus": [{"status": k, "count": v} for k, v in status_counts.items()],
        "casesByPriority": [{"priority": k, "count": v} for k, v in priority_counts.items()],
        "usersByRole": [{"role": k, "count": v} for k, v in role_counts.items()],
        "tenantsByPlan": [{"plan": k, "count": v} for k, v in plan_counts.items()],
        "tenantsByStatus": [{"status": k, "count": v} for k, v in tenant_status_counts.items()],
        "tenantBreakdown": sorted(tenant_breakdown, key=lambda x: x["cases"], reverse=True),
        "generatedAt": _now_iso(),
    }
