"""Public registration and application management.

Public endpoints (no auth):
  POST /applications/org       — submit an organization account request
  POST /applications/solo      — submit a solo dermatologist account request

Protected endpoints (platform_admin only):
  GET  /applications           — list all applications (filterable by status/type)
  GET  /applications/{id}      — get single application
  POST /applications/{id}/review — approve / reject with notes and verification level
"""

from datetime import datetime, timezone
from typing import Annotated, Any, Optional

import os
import uuid
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile

from app.auth import require_platform_admin
from app.config import settings
from app.media import public_media_url
from app.schemas import (
    OrgApplicationCreate,
    SoloDermatologistApplicationCreate,
    NurseApplicationCreate,
    FacilityDoctorApplicationCreate,
    ApplicationReview,
    SelectedPackage,
)
from app.store import store

router = APIRouter(prefix="/applications", tags=["applications"])


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Canonical package catalogue (mirrors lib/packages.ts) ────────────────────
CANONICAL_PACKAGES = [
    {"name": "Village Nurse Basic",  "amount": 80000,   "billingCycle": "monthly", "badge": "Starter",    "desc": "Frontline health workers · TZS 80,000/mo",                       "seats": "Hadi watumiaji 5",   "forTypes": ["nurse", "org"], "highlight": False},
    {"name": "Solo Pro Specialist",  "amount": 350000,  "billingCycle": "monthly", "badge": "Individual", "desc": "Solo dermatologist practice · TZS 350,000/mo",                   "seats": "Hadi watumiaji 5",   "forTypes": ["solo"],         "highlight": False},
    {"name": "Rural Clinic Hub",     "amount": 250000,  "billingCycle": "monthly", "badge": "Popular",    "desc": "Up to 5 health workers · TZS 250,000/mo",                        "seats": "Hadi watumiaji 20",  "forTypes": ["org"],          "highlight": True},
    {"name": "Regional Hospital",    "amount": 600000,  "billingCycle": "monthly", "badge": "Pro",        "desc": "Unlimited staff & priority SLA · TZS 600,000/mo",               "seats": "Hadi watumiaji 100", "forTypes": ["org"],          "highlight": False},
    {"name": "Enterprise System",    "amount": 1200000, "billingCycle": "monthly", "badge": "Enterprise", "desc": "Dedicated SLA & Custom features · TZS 1,200,000/mo",            "seats": "Watumiaji wasio na kikomo", "forTypes": ["org"],   "highlight": False},
]

def _get_canonical_amount(package_name: str) -> Optional[int]:
    pkg = next((p for p in CANONICAL_PACKAGES if p["name"] == package_name), None)
    return pkg["amount"] if pkg else None


# ── Public: GET /packages — returns canonical package list (no auth) ─────────

@router.get("/packages")
def list_packages(for_type: Optional[str] = Query(None, description="Filter by account type: org, solo, nurse")):
    """Return the canonical global package catalogue. No auth required."""
    pkgs = CANONICAL_PACKAGES
    if for_type:
        pkgs = [p for p in pkgs if for_type in p["forTypes"]]
    return pkgs


# ── Public: submit applications & registration document uploads (no auth) ─────

@router.post("/upload-document")
async def upload_application_document(
    file: UploadFile = File(...),
):
    """Public endpoint for applicants to upload passport-size photos and registration documents."""
    os.makedirs(settings.upload_dir, exist_ok=True)
    ext = os.path.splitext(file.filename or "doc.jpg")[1] or ".jpg"
    name = f"doc_{uuid.uuid4().hex[:12]}{ext}"
    path = os.path.join(settings.upload_dir, name)
    content = await file.read()
    with open(path, "wb") as f:
        f.write(content)
    relative = f"/uploads/{name}"
    return {"url": public_media_url(relative), "filename": name, "path": relative}

@router.post("/org", status_code=201)
def submit_org_application(body: OrgApplicationCreate):
    """Submit a hospital / clinic organisation account request."""
    # Prevent duplicate pending applications for the same email
    existing = next(
        (a for a in store.list_applications()
         if a.get("contactEmail", "").lower() == body.contactEmail.lower()
         and a.get("status") == "pending"),
        None,
    )
    if existing:
        raise HTTPException(
            status_code=400,
            detail="An application for this email is already pending review.",
        )
    app = store.add_application({
        **body.model_dump(),
        "applicationType": "organization",
    })
    return {
        "applicationId": app["id"],
        "status": app["status"],
        "message": (
            "Your application has been received. The SkinLink team will review it "
            "and contact you within 2–3 business days."
        ),
    }


@router.post("/solo", status_code=201)
def submit_solo_application(body: SoloDermatologistApplicationCreate):
    """Submit a solo dermatologist professional account request."""
    existing = next(
        (a for a in store.list_applications()
         if a.get("email", "").lower() == body.email.lower()
         and a.get("status") == "pending"),
        None,
    )
    if existing:
        raise HTTPException(
            status_code=400,
            detail="An application for this email is already pending review.",
        )
    app = store.add_application({
        **body.model_dump(),
        "applicationType": "solo_dermatologist",
    })
    return {
        "applicationId": app["id"],
        "status": app["status"],
        "message": (
            "Your application has been received. Professional verification involves "
            "identity, MCT registration, specialist qualification, and practice checks. "
            "You will be contacted within 3–5 business days."
        ),
    }


@router.post("/nurse", status_code=201)
def submit_nurse_application(body: NurseApplicationCreate):
    """Submit a frontline nurse / village health worker account request."""
    existing = next(
        (a for a in store.list_applications()
         if a.get("email", "").lower() == body.email.lower()
         and a.get("status") == "pending"),
        None,
    )
    if existing:
        raise HTTPException(
            status_code=400,
            detail="An application for this email is already pending review.",
        )
    app = store.add_application({
        **body.model_dump(),
        "applicationType": "nurse",
    })
    return {
        "applicationId": app["id"],
        "status": app["status"],
        "message": (
            "Your nurse application has been received. Verification involves "
            "TNMC registration, nursing licence, facility affiliation, and identity checks."
        ),
    }


@router.post("/doctor", status_code=201)
def submit_doctor_application(body: FacilityDoctorApplicationCreate):
    """Submit a facility doctor / hospital specialist account request."""
    existing = next(
        (a for a in store.list_applications()
         if a.get("email", "").lower() == body.email.lower()
         and a.get("status") == "pending"),
        None,
    )
    if existing:
        raise HTTPException(
            status_code=400,
            detail="An application for this email is already pending review.",
        )
    app = store.add_application({
        **body.model_dump(),
        "applicationType": "facility_doctor",
    })
    return {
        "applicationId": app["id"],
        "status": app["status"],
        "message": (
            "Your facility doctor application has been received. Verification involves "
            "MCT registration, practising licence, specialist qualification, and facility check."
        ),
    }


# ── Protected: platform admin review ─────────────────────────────────────────

@router.get("")
def list_applications(
    _: Annotated[dict, Depends(require_platform_admin)],
    status: Optional[str] = Query(None, description="Filter by: pending, approved, rejected"),
    type: Optional[str] = Query(None, alias="type", description="Filter by: organization, solo_dermatologist"),
):
    apps = store.list_applications(status=status)
    if type:
        apps = [a for a in apps if a.get("applicationType") == type]
    return apps


@router.get("/{app_id}")
def get_application(
    app_id: str,
    _: Annotated[dict, Depends(require_platform_admin)],
):
    app = store.get_application(app_id)
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")
    return app


@router.post("/{app_id}/review")
def review_application(
    app_id: str,
    body: ApplicationReview,
    admin: Annotated[dict, Depends(require_platform_admin)],
):
    """Approve or reject an application. On approval, provision the account automatically."""
    app = store.get_application(app_id)
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")
    if app.get("status") != "pending":
        raise HTTPException(status_code=400, detail="Application has already been reviewed")

    patch = {
        "status": body.status,
        "reviewNotes": body.reviewNotes,
        "reviewedAt": _now_iso(),
        "reviewedBy": admin["id"],
        "verificationLevel": body.verificationLevel or 0,
        "verifiedItems": body.verifiedItems or [],
    }

    provisioned = None
    if body.status == "approved":
        atype = app.get("applicationType")
        requested_pwd = app.get("requestedPassword") or "SkinLink@2025"

        if atype == "organization":
            # Auto-provision tenant + org admin account
            try:
                tenant, admin_user = store.create_tenant_account({
                    "name": app["orgName"],
                    "region": app["region"],
                    "country": app.get("country", "Tanzania"),
                    "plan": app.get("plan", "pilot"),
                    "seats": app.get("seats", 10),
                    "clinics": 1,
                    "contactName": app["contactName"],
                    "contactEmail": app["contactEmail"],
                    "adminName": app["contactName"],
                    "adminEmail": app["contactEmail"],
                    "adminPassword": requested_pwd,
                    "adminTitle": app.get("contactTitle"),
                })
                patch["provisionedTenantId"] = tenant["id"]
                patch["provisionedAdminId"] = admin_user["id"]
                provisioned = {"tenant": tenant, "admin": admin_user}
            except Exception as exc:
                raise HTTPException(status_code=500, detail=f"Provisioning failed: {exc}") from exc

        elif atype == "solo_dermatologist":
            # Provision a solo tenant + specialist account
            try:
                practice_name = app.get("practiceName") or f"Dr. {app['fullName'].split()[-1]} Dermatology"
                tenant, specialist_user = store.create_tenant_account({
                    "name": practice_name,
                    "region": app["region"],
                    "country": app.get("country", "Tanzania"),
                    "plan": "pilot",
                    "seats": 5,
                    "clinics": 1,
                    "contactName": app["fullName"],
                    "contactEmail": app["email"],
                    "adminName": app["fullName"],
                    "adminEmail": app["email"],
                    "adminPassword": requested_pwd,
                    "adminTitle": app.get("professionalTitle"),
                    "primaryColor": "#0c6b58",
                })
                # Upgrade the auto-created user to specialist + org_admin
                store.update_user(specialist_user["id"], {
                    "role": "specialist",
                    "specialty": app.get("specialty", "Dermatology"),
                    "mctNumber": app.get("mctRegistrationNumber"),
                    "licenceNumber": app.get("licenceNumber"),
                    "licenceExpiry": app.get("licenceExpiry"),
                    "verificationLevel": body.verificationLevel or 3,
                    "accountType": "solo_dermatologist",
                })
                patch["provisionedTenantId"] = tenant["id"]
                patch["provisionedUserId"] = specialist_user["id"]
                provisioned = {"tenant": tenant, "user": specialist_user}
            except Exception as exc:
                raise HTTPException(status_code=500, detail=f"Provisioning failed: {exc}") from exc

        elif atype in ("nurse", "facility_doctor"):
            # Provision user in default network (Mwanza or first tenant)
            try:
                tenant = store.db["tenants"][0] if store.db["tenants"] else None
                tenant_id = tenant["id"] if tenant else "t_mwanza"
                role = "specialist" if atype == "facility_doctor" else "clinician"
                new_user = store.add_user({
                    "tenantId": tenant_id,
                    "name": app["fullName"],
                    "email": app["email"],
                    "role": role,
                    "title": app.get("professionalTitle") or app.get("nursingQualification") or ("Nurse" if atype == "nurse" else "Medical Officer"),
                    "phone": app.get("phone"),
                    "status": "active",
                    "avatarColor": "#1f7a8c",
                }, requested_pwd)
                patch["provisionedTenantId"] = tenant_id
                patch["provisionedUserId"] = new_user["id"]
                provisioned = {"user": new_user}
            except Exception as exc:
                raise HTTPException(status_code=500, detail=f"Provisioning failed: {exc}") from exc

    updated = store.update_application(app_id, patch)
    return {"application": updated, "provisioned": provisioned}


# ── Global package price management (platform_admin) ─────────────────────────

@router.patch("/packages/{package_name}")
def update_global_package(
    package_name: str,
    payload: SelectedPackage,
    admin: Annotated[dict, Depends(require_platform_admin)],
):
    """
    Update the global price / billing cycle for a named package.

    This updates CANONICAL_PACKAGES in memory for the running process AND
    propagates the new amount to every approved application and provisioned
    tenant that is currently on this package — making it truly global.
    """
    # Find in our canonical list
    pkg = next((p for p in CANONICAL_PACKAGES if p["name"] == package_name), None)
    if not pkg:
        raise HTTPException(status_code=404, detail=f"Package '{package_name}' not found in catalogue")

    # Update in-memory catalogue
    pkg["amount"] = payload.amount
    pkg["billingCycle"] = payload.billingCycle
    if payload.packageName and payload.packageName != package_name:
        pkg["name"] = payload.packageName   # allow renaming

    updated_name = pkg["name"]
    new_amount = pkg["amount"]
    new_cycle = pkg["billingCycle"]

    # Propagate to all applications that have this package
    updated_apps = 0
    for app in store.list_applications():
        existing = app.get("selectedPackage")
        if existing and existing.get("packageName") == package_name:
            store.update_application(app["id"], {
                "selectedPackage": {
                    **existing,
                    "packageName": updated_name,
                    "amount": new_amount,
                    "billingCycle": new_cycle,
                },
                "packageUpdatedAt": _now_iso(),
                "packageUpdatedBy": admin["name"],
            })
            # Also update the provisioned tenant
            tenant_id = app.get("provisionedTenantId")
            if tenant_id:
                store.update_tenant(tenant_id, {
                    "plan": updated_name,
                    "selectedPackage": {
                        "packageName": updated_name,
                        "amount": new_amount,
                        "currency": "TZS",
                        "billingCycle": new_cycle,
                    },
                })
            updated_apps += 1

    return {
        "package": pkg,
        "updatedApplications": updated_apps,
        "updatedBy": admin["name"],
        "updatedAt": _now_iso(),
        "message": f"Package '{updated_name}' updated globally. {updated_apps} client account(s) updated.",
    }


# ── Payment & Document Verification Endpoints (platform_admin) ────────────────

@router.post("/{app_id}/update-package")
def update_application_package(
    app_id: str,
    payload: dict[str, Any],
    admin: Annotated[dict, Depends(require_platform_admin)],
):
    """Provider action: Update the subscription package and/or billing amount for a client."""
    app = store.get_application(app_id)
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")

    pkg_name = payload.get("packageName")
    amount = payload.get("amount")
    currency = payload.get("currency", "TZS")
    billing_cycle = payload.get("billingCycle", "monthly")

    if not pkg_name or amount is None:
        raise HTTPException(status_code=400, detail="packageName and amount are required")

    new_pkg = {
        "packageName": pkg_name,
        "amount": float(amount),
        "currency": currency,
        "billingCycle": billing_cycle,
    }

    patch = {
        "selectedPackage": new_pkg,
        "packageUpdatedAt": _now_iso(),
        "packageUpdatedBy": admin["name"],
    }

    # Also update tenant billing metadata if provisioned
    tenant_id = app.get("provisionedTenantId")
    if tenant_id:
        store.update_tenant(tenant_id, {
            "plan": pkg_name,
            "selectedPackage": new_pkg,
        })

    updated = store.update_application(app_id, patch)
    return {"application": updated, "selectedPackage": new_pkg}



@router.post("/{app_id}/record-payment")
def record_application_payment(
    app_id: str,
    payload: dict[str, Any],
    admin: Annotated[dict, Depends(require_platform_admin)],
):
    """Record an external payment (M-Pesa / Bank / Control Number) for a client application or tenant."""
    app = store.get_application(app_id)
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")

    ref_code = payload.get("paymentReference") or f"PAY-{uuid.uuid4().hex[:8].upper()}"
    amount = float(payload.get("amountPaid", 0))
    method = payload.get("paymentMethod", "M-Pesa / Bank")
    valid_until = payload.get("validUntil") or _now_iso()
    notes = payload.get("notes", "External payment verified by provider")

    payment_record = {
        "id": f"pay_{uuid.uuid4().hex[:8]}",
        "paymentReference": ref_code,
        "amountPaid": amount,
        "paymentMethod": method,
        "billingCycle": payload.get("billingCycle", "monthly"),
        "recordedAt": _now_iso(),
        "recordedBy": admin["name"],
        "validUntil": valid_until,
        "notes": notes,
    }

    history = app.get("paymentHistory", [])
    history.insert(0, payment_record)

    patch = {
        "paymentStatus": "paid",
        "serviceAccess": "active",
        "paymentReference": ref_code,
        "amountPaid": amount,
        "paymentExpiryDate": valid_until,
        "paymentHistory": history,
    }

    # Also update provisioned tenant if already provisioned
    tenant_id = app.get("provisionedTenantId")
    if tenant_id:
        store.update_tenant(tenant_id, {
            "status": "active",
            "paymentStatus": "paid",
            "serviceAccess": "active",
            "paymentExpiryDate": valid_until,
        })

    updated = store.update_application(app_id, patch)
    return {"application": updated, "paymentRecord": payment_record}


@router.post("/{app_id}/toggle-service-block")
def toggle_service_block(
    app_id: str,
    payload: dict[str, Any],
    admin: Annotated[dict, Depends(require_platform_admin)],
):
    """Provider control: Block or Unblock service access for overdue payment or compliance."""
    app = store.get_application(app_id)
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")

    current_access = app.get("serviceAccess", "active")
    new_access = "blocked" if current_access == "active" else "active"
    block_reason = payload.get("reason", "Payment overdue / Provider service control")

    patch = {
        "serviceAccess": new_access,
        "blockReason": block_reason if new_access == "blocked" else None,
        "blockedAt": _now_iso() if new_access == "blocked" else None,
        "blockedBy": admin["name"] if new_access == "blocked" else None,
    }

    tenant_id = app.get("provisionedTenantId")
    if tenant_id:
        tenant_status = "suspended" if new_access == "blocked" else "active"
        store.update_tenant(tenant_id, {
            "status": tenant_status,
            "serviceAccess": new_access,
        })

    updated = store.update_application(app_id, patch)
    return {"application": updated, "serviceAccess": new_access}


@router.post("/{app_id}/send-message")
def send_application_message(
    app_id: str,
    payload: dict[str, Any],
    admin: Annotated[dict, Depends(require_platform_admin)],
):
    """Send official payment reminder or verification notice message to client web portal."""
    app = store.get_application(app_id)
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")

    msg_text = payload.get("message", "").strip()
    if not msg_text:
        raise HTTPException(status_code=400, detail="Message required")

    msg_obj = {
        "id": f"msg_{uuid.uuid4().hex[:8]}",
        "sender": "Platform Provider",
        "senderName": admin["name"],
        "body": msg_text,
        "category": payload.get("category", "payment_notice"),
        "sentAt": _now_iso(),
        "read": False,
    }

    messages = app.get("messages", [])
    messages.insert(0, msg_obj)

    updated = store.update_application(app_id, {"messages": messages})

    # Also push message to provisioned tenant user inbox
    tenant_id = app.get("provisionedTenantId")
    if tenant_id:
        store.add_tenant_message(tenant_id, msg_obj)

    return {"application": updated, "message": msg_obj}


@router.post("/{app_id}/verify-document")
def verify_application_document(
    app_id: str,
    payload: dict[str, Any],
    admin: Annotated[dict, Depends(require_platform_admin)],
):
    """Verify or flag a specific uploaded document directly in the provider workspace."""
    app = store.get_application(app_id)
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")

    doc_type = payload.get("docType") or payload.get("docId")
    verified = payload.get("verified", True)
    notes = payload.get("notes", "")

    documents = app.get("documents", []) or []
    updated_docs = []
    found = False

    for d in documents:
        if d.get("type") == doc_type or d.get("id") == doc_type or d.get("label") == doc_type:
            d["verified"] = verified
            d["verificationNotes"] = notes
            d["verifiedAt"] = _now_iso()
            d["verifiedBy"] = admin["name"]
            found = True
        updated_docs.append(d)

    if not found and payload.get("url"):
        updated_docs.append({
            "id": doc_type or f"doc_{uuid.uuid4().hex[:6]}",
            "type": doc_type or "verification_doc",
            "label": payload.get("label", "Uploaded Verification Document"),
            "url": payload.get("url"),
            "verified": verified,
            "verificationNotes": notes,
            "verifiedAt": _now_iso(),
        })

    # Calculate overall verification count
    verified_count = len([d for d in updated_docs if d.get("verified")])
    updated = store.update_application(app_id, {
        "documents": updated_docs,
        "verifiedItems": [d["type"] for d in updated_docs if d.get("verified")],
        "verificationLevel": min(5, verified_count),
    })

    return {"application": updated, "documents": updated_docs}
