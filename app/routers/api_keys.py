"""
SkinLink External API Key Management
=====================================
Endpoints:
  Public (no auth):
    POST /api-access/apply          — Submit an API access application

  Platform admin:
    GET  /api-access/applications   — List all API access applications
    GET  /api-access/applications/{id} — Get single application
    POST /api-access/applications/{id}/approve — Approve + issue key
    POST /api-access/applications/{id}/reject  — Reject with reason
    GET  /api-access/keys           — List all issued keys
    GET  /api-access/keys/{key_id}  — Get key details + usage
    POST /api-access/keys/{key_id}/rotate — Rotate (reissue) a key
    POST /api-access/keys/{key_id}/revoke  — Revoke a key
    PATCH /api-access/keys/{key_id}/limits — Update rate/quota limits

  Key-holder (self-service, authenticated via Bearer API key):
    GET  /api-access/me             — Return own key info + usage
    POST /api-access/me/rotate      — Self-service key rotation
"""

import hashlib
import secrets
import uuid
from datetime import datetime, timezone
from typing import Annotated, Any, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, EmailStr

from app.auth import get_current_user, require_platform_admin
from app.store import store

router = APIRouter(prefix="/api-access", tags=["api-keys"])


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _uid(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


def _generate_key() -> tuple[str, str]:
    """Return (raw_key, key_hash).  Only raw_key is shown once; hash is stored."""
    raw = "sk_live_" + secrets.token_urlsafe(32)
    hashed = hashlib.sha256(raw.encode()).hexdigest()
    return raw, hashed


# ── Pricing tiers (mirrors lib/packages.ts) ───────────────────────────────────
API_TIERS = [
    {
        "id": "free",
        "name": "Developer / Free",
        "priceMonthly": 0,
        "currency": "TZS",
        "requestsPerMonth": 500,
        "requestsPerMinute": 10,
        "scopes": ["cases:read", "patients:read"],
        "support": "Community forum",
        "badge": "Free",
    },
    {
        "id": "starter",
        "name": "Starter",
        "priceMonthly": 150_000,
        "currency": "TZS",
        "requestsPerMonth": 10_000,
        "requestsPerMinute": 60,
        "scopes": ["cases:read", "cases:write", "patients:read", "patients:write", "referrals:read"],
        "support": "Email (48 h SLA)",
        "badge": "Starter",
    },
    {
        "id": "growth",
        "name": "Growth",
        "priceMonthly": 400_000,
        "currency": "TZS",
        "requestsPerMonth": 100_000,
        "requestsPerMinute": 300,
        "scopes": ["cases:read", "cases:write", "patients:read", "patients:write",
                   "referrals:read", "referrals:write", "ai:assessments", "webhooks"],
        "support": "Email (24 h SLA)",
        "badge": "Growth",
    },
    {
        "id": "enterprise",
        "name": "Enterprise",
        "priceMonthly": 0,   # negotiated
        "currency": "TZS",
        "requestsPerMonth": -1,   # unlimited
        "requestsPerMinute": -1,
        "scopes": ["*"],
        "support": "Dedicated account manager",
        "badge": "Enterprise",
        "custom": True,
    },
]

ALL_SCOPES = [
    {"key": "cases:read",       "desc": "Read cases, images, notes"},
    {"key": "cases:write",      "desc": "Create and update cases"},
    {"key": "patients:read",    "desc": "Read patient demographics and consent records"},
    {"key": "patients:write",   "desc": "Register and update patients"},
    {"key": "referrals:read",   "desc": "Read referral status and history"},
    {"key": "referrals:write",  "desc": "Submit referrals programmatically"},
    {"key": "ai:assessments",   "desc": "Trigger AI skin assessments via API"},
    {"key": "webhooks",         "desc": "Register and manage webhook endpoints"},
    {"key": "fhir:r4",          "desc": "FHIR R4 export endpoints (Patient, DiagnosticReport)"},
]


# ── Public endpoints ─────────────────────────────────────────────────────────

@router.get("/tiers")
def list_tiers():
    """Return the public API pricing catalogue. No auth required."""
    return API_TIERS


@router.get("/scopes")
def list_scopes():
    """Return available OAuth-style scopes. No auth required."""
    return ALL_SCOPES


class ApiAccessApplication(BaseModel):
    # Applicant
    orgName: str
    contactName: str
    email: EmailStr
    phone: Optional[str] = None
    website: Optional[str] = None
    country: str = "Tanzania"
    # Technical
    tierId: str = "starter"
    intendedUse: str
    integrationType: str   # "EMR", "Custom App", "Mobile", "Research", "Other"
    expectedMonthlyRequests: Optional[int] = None
    technicalContactEmail: Optional[EmailStr] = None
    # Legal
    agreeTerms: bool = False
    agreeDataPolicy: bool = False


@router.post("/apply", status_code=201)
def apply_for_api_access(body: ApiAccessApplication):
    """Public: Submit an API access application. No auth required."""
    if not body.agreeTerms or not body.agreeDataPolicy:
        raise HTTPException(status_code=422, detail="Terms and data policy acceptance required")
    tier = next((t for t in API_TIERS if t["id"] == body.tierId), None)
    if not tier:
        raise HTTPException(status_code=400, detail=f"Unknown tier: {body.tierId}")
    existing = next(
        (a for a in store.list_api_key_applications()
         if a.get("email", "").lower() == body.email.lower() and a.get("status") == "pending"),
        None,
    )
    if existing:
        raise HTTPException(status_code=400, detail="A pending application for this email already exists.")
    app = store.add_api_key_application({
        **body.model_dump(),
        "tierName": tier["name"],
        "tierPriceMonthly": tier["priceMonthly"],
        "requestedScopes": tier["scopes"],
    })
    return {
        "applicationId": app["id"],
        "status": "pending",
        "message": (
            "Your API access application has been received. "
            "The SkinLink team will review it within 2 business days. "
            "You'll receive credentials by email once approved."
        ),
    }


# ── Platform admin endpoints ──────────────────────────────────────────────────

@router.get("/applications")
def list_api_applications(
    _: Annotated[dict, Depends(require_platform_admin)],
    status: Optional[str] = Query(None),
):
    apps = store.list_api_key_applications(status=status)
    return apps


@router.get("/applications/{app_id}")
def get_api_application(app_id: str, _: Annotated[dict, Depends(require_platform_admin)]):
    app = store.get_api_key_application(app_id)
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")
    return app


class ApproveApiApplication(BaseModel):
    tierId: str = "starter"
    customScopes: Optional[list[str]] = None
    customLimits: Optional[dict[str, int]] = None   # {"requestsPerMonth": x, "requestsPerMinute": y}
    notes: Optional[str] = None
    billingReference: Optional[str] = None


@router.post("/applications/{app_id}/approve")
def approve_api_application(
    app_id: str,
    body: ApproveApiApplication,
    admin: Annotated[dict, Depends(require_platform_admin)],
):
    """Approve an API application and issue credentials."""
    app = store.get_api_key_application(app_id)
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")
    if app.get("status") != "pending":
        raise HTTPException(status_code=400, detail="Application is not in pending state")

    tier = next((t for t in API_TIERS if t["id"] == body.tierId), None)
    if not tier:
        raise HTTPException(status_code=400, detail=f"Unknown tier: {body.tierId}")

    raw_key, key_hash = _generate_key()
    limits = body.customLimits or {
        "requestsPerMonth": tier["requestsPerMonth"],
        "requestsPerMinute": tier["requestsPerMinute"],
    }
    scopes = body.customScopes or tier["scopes"]

    api_key = store.add_api_key({
        "applicationId": app_id,
        "orgName": app["orgName"],
        "contactName": app["contactName"],
        "email": app["email"],
        "tierId": body.tierId,
        "tierName": tier["name"],
        "scopes": scopes,
        "limits": limits,
        "keyHash": key_hash,
        "keyPrefix": raw_key[:14] + "…",  # for display
        "status": "active",
        "requestsThisMonth": 0,
        "requestsTotal": 0,
        "billingReference": body.billingReference,
        "notes": body.notes,
    })

    store.update_api_key_application(app_id, {
        "status": "approved",
        "reviewedAt": _now_iso(),
        "reviewedBy": admin["name"],
        "issuedKeyId": api_key["id"],
        "notes": body.notes,
    })

    return {
        "apiKey": api_key,
        "rawKey": raw_key,   # shown ONCE — must be copied by admin / sent to client
        "message": "API key issued. Store the rawKey securely — it will not be shown again.",
    }


class RejectApiApplication(BaseModel):
    reason: str


@router.post("/applications/{app_id}/reject")
def reject_api_application(
    app_id: str,
    body: RejectApiApplication,
    admin: Annotated[dict, Depends(require_platform_admin)],
):
    app = store.get_api_key_application(app_id)
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")
    store.update_api_key_application(app_id, {
        "status": "rejected",
        "reviewedAt": _now_iso(),
        "reviewedBy": admin["name"],
        "rejectionReason": body.reason,
    })
    return {"status": "rejected", "reason": body.reason}


@router.get("/keys")
def list_api_keys(_: Annotated[dict, Depends(require_platform_admin)]):
    return store.list_api_keys()


@router.get("/keys/{key_id}")
def get_api_key(key_id: str, _: Annotated[dict, Depends(require_platform_admin)]):
    key = store.get_api_key(key_id)
    if not key:
        raise HTTPException(status_code=404, detail="API key not found")
    return key


@router.post("/keys/{key_id}/rotate")
def rotate_api_key(key_id: str, admin: Annotated[dict, Depends(require_platform_admin)]):
    """Issue a new key value while preserving the key record and scopes."""
    key = store.get_api_key(key_id)
    if not key:
        raise HTTPException(status_code=404, detail="API key not found")
    raw_key, key_hash = _generate_key()
    store.update_api_key(key_id, {
        "keyHash": key_hash,
        "keyPrefix": raw_key[:14] + "…",
        "rotatedAt": _now_iso(),
        "rotatedBy": admin["name"],
    })
    return {"rawKey": raw_key, "message": "Key rotated. Store the new rawKey securely."}


@router.post("/keys/{key_id}/revoke")
def revoke_api_key(key_id: str, admin: Annotated[dict, Depends(require_platform_admin)]):
    key = store.get_api_key(key_id)
    if not key:
        raise HTTPException(status_code=404, detail="API key not found")
    store.update_api_key(key_id, {"status": "revoked", "revokedAt": _now_iso()})
    return {"status": "revoked"}


class UpdateKeyLimits(BaseModel):
    requestsPerMonth: Optional[int] = None
    requestsPerMinute: Optional[int] = None


@router.patch("/keys/{key_id}/limits")
def update_key_limits(
    key_id: str,
    body: UpdateKeyLimits,
    _: Annotated[dict, Depends(require_platform_admin)],
):
    key = store.get_api_key(key_id)
    if not key:
        raise HTTPException(status_code=404, detail="API key not found")
    limits = dict(key.get("limits", {}))
    if body.requestsPerMonth is not None:
        limits["requestsPerMonth"] = body.requestsPerMonth
    if body.requestsPerMinute is not None:
        limits["requestsPerMinute"] = body.requestsPerMinute
    store.update_api_key(key_id, {"limits": limits})
    return store.get_api_key(key_id)


# ── Key-holder self-service (authenticate via API key in Authorization header) ─

def _get_key_from_bearer(authorization: Optional[str] = Header(None)) -> dict:
    if not authorization or not authorization.startswith("Bearer sk_live_"):
        raise HTTPException(status_code=401, detail="Valid API key required (Bearer sk_live_…)")
    raw = authorization.removeprefix("Bearer ")
    key_hash = hashlib.sha256(raw.encode()).hexdigest()
    api_key = store.get_api_key_by_hash(key_hash)
    if not api_key:
        raise HTTPException(status_code=401, detail="API key not found or revoked")
    if api_key.get("status") != "active":
        raise HTTPException(status_code=403, detail=f"API key is {api_key.get('status')}")
    return api_key


@router.get("/me")
def get_my_key_info(api_key: Annotated[dict, Depends(_get_key_from_bearer)]):
    """Key holder: return own key info and usage statistics."""
    safe = {k: v for k, v in api_key.items() if k != "keyHash"}
    return safe


@router.post("/me/rotate")
def self_rotate_key(api_key: Annotated[dict, Depends(_get_key_from_bearer)]):
    """Key holder: self-service key rotation."""
    raw_key, key_hash = _generate_key()
    store.update_api_key(api_key["id"], {
        "keyHash": key_hash,
        "keyPrefix": raw_key[:14] + "…",
        "rotatedAt": _now_iso(),
        "rotatedBy": api_key.get("email", "self"),
    })
    return {"rawKey": raw_key, "message": "Key rotated. Update your integration immediately."}


# ── Usage tracking helper (called by other routers) ───────────────────────────

def record_api_usage(key_hash: str) -> None:
    """Increment usage counters on a key. Called by API middleware."""
    key = store.get_api_key_by_hash(key_hash)
    if key:
        store.update_api_key(key["id"], {
            "requestsThisMonth": key.get("requestsThisMonth", 0) + 1,
            "requestsTotal": key.get("requestsTotal", 0) + 1,
            "lastUsedAt": _now_iso(),
        })
