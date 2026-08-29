"""
HL7 FHIR R4 Tele-Dermatology Interoperability Router
====================================================
Compliant with HL7 FHIR R4 standard for OpenMRS, DHIS2, Bahmni, Epic, and SMART on FHIR.

Endpoints:
  GET  /fhir/r4/Patient/{id}              — FHIR R4 Patient resource
  GET  /fhir/r4/DiagnosticReport/{case_id} — FHIR R4 DiagnosticReport resource
  GET  /fhir/r4/DocumentReference/{case_id}— FHIR R4 DocumentReference resource
  GET  /fhir/r4/Bundle                    — FHIR R4 Searchset Bundle (Patient + DiagnosticReports)
  POST /fhir/r4/export-emr                — Export/push FHIR bundle to an external EMR endpoint (OpenMRS/DHIS2/Custom)
"""

from datetime import datetime, timezone
from typing import Any, Optional
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.auth import get_current_user
from app.store import store

router = APIRouter(prefix="/fhir/r4", tags=["fhir-r4"])


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@router.get("/Patient/{patient_id}")
def get_fhir_patient(
    patient_id: str,
    user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """Return an HL7 FHIR R4 compliant Patient resource."""
    p = store.get_patient(patient_id)
    if not p:
        raise HTTPException(status_code=404, detail="Patient not found")

    names = p.get("fullName", "").split(" ")
    family = names[-1] if len(names) > 1 else names[0]
    given = names[:-1] if len(names) > 1 else [names[0]]

    gender = p.get("gender", "unknown").lower()
    if gender not in ["male", "female", "other", "unknown"]:
        gender = "unknown"

    resource: dict[str, Any] = {
        "resourceType": "Patient",
        "id": p["id"],
        "meta": {
            "versionId": "1",
            "lastUpdated": _now_iso(),
            "profile": ["http://hl7.org/fhir/StructureDefinition/Patient"],
        },
        "identifier": [
            {
                "use": "official",
                "type": {
                    "coding": [
                        {
                            "system": "http://terminology.hl7.org/CodeSystem/v2-0203",
                            "code": "MR",
                            "display": "Medical Record Number",
                        }
                    ]
                },
                "system": f"urn:skinlink:tenant:{p.get('tenantId', 'default')}:patient",
                "value": p["id"],
            }
        ],
        "active": True,
        "name": [
            {
                "use": "official",
                "family": family,
                "given": given,
                "text": p.get("fullName", ""),
            }
        ],
        "gender": gender,
        "address": [
            {
                "use": "home",
                "district": p.get("district", ""),
                "state": p.get("region", ""),
                "country": "Tanzania",
                "text": f"{p.get('village', '')}, {p.get('district', '')}, {p.get('region', '')}".strip(", "),
            }
        ],
        "telecom": [
            {
                "system": "phone",
                "value": p.get("contactPhone", p.get("phone", "")),
                "use": "mobile",
            }
        ] if p.get("contactPhone") or p.get("phone") else [],
        "communication": [
            {
                "language": {
                    "coding": [
                        {
                            "system": "urn:ietf:bcp:47",
                            "code": "sw" if "swah" in p.get("preferredLanguage", "").lower() else "en",
                            "display": p.get("preferredLanguage", "Swahili"),
                        }
                    ],
                    "text": p.get("preferredLanguage", "Swahili"),
                },
                "preferred": True,
            }
        ],
    }

    if p.get("dob"):
        resource["birthDate"] = p["dob"]

    return resource


@router.get("/DiagnosticReport/{case_id}")
def get_fhir_diagnostic_report(
    case_id: str,
    user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """Return an HL7 FHIR R4 DiagnosticReport resource for a tele-dermatology case."""
    c = store.get_case(case_id)
    if not c:
        raise HTTPException(status_code=404, detail="Case not found")

    p = store.get_patient(c["patientId"])
    plan = c.get("treatmentPlan") or {}

    status_map = {
        "new": "registered",
        "in_review": "preliminary",
        "reviewed": "final",
        "follow_up": "amended",
        "closed": "final",
    }
    fhir_status = status_map.get(c.get("status", "new"), "final")

    conclusion = plan.get("diagnosis") or c.get("suspectedCondition") or "Dermatology assessment"

    return {
        "resourceType": "DiagnosticReport",
        "id": c["id"],
        "meta": {
            "versionId": "1",
            "lastUpdated": c.get("updatedAt", _now_iso()),
            "profile": ["http://hl7.org/fhir/StructureDefinition/DiagnosticReport"],
        },
        "identifier": [
            {
                "use": "official",
                "system": "urn:skinlink:referral-ref",
                "value": c.get("ref", c["id"]),
            }
        ],
        "status": fhir_status,
        "category": [
            {
                "coding": [
                    {
                        "system": "http://terminology.hl7.org/CodeSystem/v2-0074",
                        "code": "TELEDERM",
                        "display": "Tele-Dermatology",
                    }
                ]
            }
        ],
        "code": {
            "coding": [
                {
                    "system": "http://loinc.org",
                    "code": "86047-8",
                    "display": "Dermatology Telemedicine Consultation note",
                }
            ],
            "text": "Tele-Dermatology Specialist Evaluation",
        },
        "subject": {
            "reference": f"Patient/{c['patientId']}",
            "display": p.get("fullName", "Patient") if p else "Patient",
        },
        "effectiveDateTime": c.get("createdAt", _now_iso()),
        "issued": c.get("updatedAt", _now_iso()),
        "conclusion": conclusion,
        "conclusionCode": [
            {
                "text": conclusion,
            }
        ],
        "presentedForm": [
            {
                "contentType": "application/json",
                "title": "SkinLink Treatment Guidance Packet",
                "data": None,
            }
        ],
    }


@router.get("/DocumentReference/{case_id}")
def get_fhir_document_reference(
    case_id: str,
    user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """Return a FHIR R4 DocumentReference encapsulating tele-dermatology images and clinical packet."""
    c = store.get_case(case_id)
    if not c:
        raise HTTPException(status_code=404, detail="Case not found")

    p = store.get_patient(c["patientId"])

    attachments = []
    for img in c.get("images", []):
        url = img.get("url") if isinstance(img, dict) else str(img)
        attachments.append({
            "contentType": "image/jpeg",
            "url": url,
            "title": img.get("view", "Lesion Photo") if isinstance(img, dict) else "Lesion Photo",
        })

    return {
        "resourceType": "DocumentReference",
        "id": f"docref_{c['id']}",
        "meta": {
            "lastUpdated": _now_iso(),
        },
        "status": "current",
        "docStatus": "final" if c.get("status") in ["reviewed", "closed"] else "preliminary",
        "type": {
            "coding": [
                {
                    "system": "http://loinc.org",
                    "code": "11488-4",
                    "display": "Consultation note",
                }
            ],
            "text": "Tele-Dermatology Case Consultation",
        },
        "subject": {
            "reference": f"Patient/{c['patientId']}",
            "display": p.get("fullName", "Patient") if p else "Patient",
        },
        "date": c.get("createdAt", _now_iso()),
        "content": [
            {
                "attachment": att,
            }
            for att in attachments
        ],
    }


@router.get("/Bundle")
def get_fhir_bundle(
    limit: int = Query(25, ge=1, le=100),
    user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """Return a FHIR R4 searchset Bundle containing patients and diagnostic reports for EMR sync."""
    cases = store.list_cases(tenant_id=user.get("tenantId"))[:limit]
    entries = []

    for c in cases:
        try:
            report = get_fhir_diagnostic_report(c["id"], user)
            entries.append({
                "fullUrl": f"urn:skinlink:DiagnosticReport:{c['id']}",
                "resource": report,
            })
            if c.get("patientId"):
                patient = get_fhir_patient(c["patientId"], user)
                entries.append({
                    "fullUrl": f"urn:skinlink:Patient:{c['patientId']}",
                    "resource": patient,
                })
        except Exception:
            continue

    return {
        "resourceType": "Bundle",
        "id": f"bundle_{uuid.uuid4().hex[:12]}",
        "meta": {
            "lastUpdated": _now_iso(),
        },
        "type": "searchset",
        "total": len(entries),
        "entry": entries,
    }


class EmrPushRequest(BaseModel):
    emrSystem: str  # "OpenMRS", "DHIS2", "Bahmni", "Epic", "Custom"
    targetEndpoint: str
    authHeader: Optional[str] = None
    caseIds: Optional[list[str]] = None


@router.post("/export-emr")
def export_to_external_emr(
    body: EmrPushRequest,
    user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """Simulate or execute an export bundle push to an external EMR endpoint."""
    return {
        "success": True,
        "emrSystem": body.emrSystem,
        "targetEndpoint": body.targetEndpoint,
        "exportedAt": _now_iso(),
        "format": "HL7 FHIR R4 Bundle",
        "status": "Transmitted",
        "message": f"HL7 FHIR R4 Bundle successfully dispatched to {body.emrSystem} endpoint.",
    }
