import os
import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from app.auth import get_current_user, get_effective_tenant_id, require_tenant
from app.config import settings
from app.schemas import CaseCreate, CaseNoteCreate, CaseUpdate
from app.store import store
from app.routers.ai import run_image_quality_checks_for_case, run_ai_assessment_for_case
from app.services.ai_service import gemini_service

router = APIRouter(prefix="/cases", tags=["cases"])


def _build_clinical_input_from_case(case: dict[str, Any], patient: dict[str, Any] | None = None) -> dict[str, Any]:
    age = None
    sex = None
    if patient:
        age = patient.get("age")
        g = patient.get("gender")
        if isinstance(g, str):
            sex = g.lower() if g.lower() in ("male", "female", "other") else None
    return {
        "patient_age": age,
        "sex": sex,
        "symptoms": [],
        "duration": None,
        "duration_days": case.get("durationDays"),
        "body_site": case.get("bodySite"),
        "severity": None,
        "previous_treatment": case.get("previousTreatment"),
        "treatment_response": None,
        "adherence": None,
        "red_flags": case.get("redFlags") or [],
        "primary_concern": case.get("primaryConcern"),
        "clinical_info": case.get("clinicalInfo"),
        "language": case.get("language") or (patient.get("language") if patient else "English"),
        "case_id": case.get("id"),
    }


def _collect_case_image_urls(case: dict[str, Any]) -> list[str]:
    urls: list[str] = []
    for img in case.get("images", []) or []:
        url = img.get("url")
        if url and url not in urls:
            urls.append(url)
    return urls


def _trigger_ai_workflow_for_case(case: dict[str, Any], patient: dict[str, Any] | None = None, tenant_id: str | None = None) -> dict[str, Any]:
    """Run AI workflow (quality check FIRST, then conditional skin assessment).

    Delegates to run_ai_assessment_for_case which internally runs the quality gate.
    Reads persisted quality result back from the case to avoid double-invocation.
    Returns a workflow status dict. Live Gemini failures are reported — never mocked.
    """
    from app.services.ai_service import GeminiServiceError

    clinical_input = _build_clinical_input_from_case(case, patient)
    image_urls = _collect_case_image_urls(case)

    try:
        ai_result = run_ai_assessment_for_case(case["id"], clinical_input, image_urls)
    except GeminiServiceError as exc:
        return {
            "qualitySummary": None,
            "aiAssessmentRan": False,
            "aiAssessment": None,
            "error": {"code": exc.code, "message": exc.message},
        }
    except Exception as exc:
        return {
            "qualitySummary": None,
            "aiAssessmentRan": False,
            "aiAssessment": None,
            "error": {"code": "ai_error", "message": str(exc)},
        }

    ai_ran = ai_result is not None

    quality_summary = None
    if tenant_id:
        refreshed = next((c for c in store.scope(tenant_id, "cases") if c.get("id") == case["id"]), None)
        if refreshed:
            quality_summary = refreshed.get("aiImageQuality")
    if quality_summary is None:
        refreshed = next((c for c in store.db.get("cases", []) if c.get("id") == case["id"]), None)
        if refreshed:
            quality_summary = refreshed.get("aiImageQuality")

    return {
        "qualitySummary": quality_summary,
        "aiAssessmentRan": ai_ran,
        "aiAssessment": ai_result,
        "error": None if ai_ran else (
            {
                "code": "image_quality_failed",
                "message": "Image quality check did not pass; retake required before AI assessment.",
            }
            if quality_summary and not quality_summary.get("pass", True)
            else None
        ),
    }


def _list_cases(user: dict, tenant_id: str | None) -> list:
    if user["role"] == "platform_admin" and not tenant_id:
        return store.scope(None, "cases")
    if not tenant_id:
        raise HTTPException(status_code=400, detail="Select a tenant")
    cases = store.scope(tenant_id, "cases")
    # Specialists only see cases assigned to them
    if user["role"] == "specialist":
        cases = [c for c in cases if c.get("specialistId") == user["id"]]
    return cases


@router.get("/specialists")
def list_specialists(
    user: Annotated[dict, Depends(get_current_user)],
    tenant_id: Annotated[str | None, Depends(get_effective_tenant_id)],
):
    """Return active specialists for the current tenant with their open-case load."""
    effective_tid = tenant_id or user.get("tenantId")
    if not effective_tid:
        raise HTTPException(status_code=400, detail="Tenant context required")
    return store.list_specialists(effective_tid)


@router.get("")
def list_cases(
    user: Annotated[dict, Depends(get_current_user)],
    tenant_id: Annotated[str | None, Depends(get_effective_tenant_id)],
):
    return _list_cases(user, tenant_id)


@router.get("/dashboard")
def dashboard_stats(
    user: Annotated[dict, Depends(get_current_user)],
    tenant_id: Annotated[str | None, Depends(get_effective_tenant_id)],
):
    cases = _list_cases(user, tenant_id)
    referrals = store.scope(tenant_id, "referrals") if tenant_id else store.scope(None, "referrals")
    follow_ups = store.scope(tenant_id, "followUps") if tenant_id else store.scope(None, "followUps")
    return {
        "newCount": len([c for c in cases if c["status"] == "new"]),
        "awaitingReview": len([c for c in cases if c["status"] == "in_review"]),
        "completed": len([c for c in cases if c["status"] in ("reviewed", "closed")]),
        "guidanceReady": len([c for c in cases if c.get("treatmentPlan")]),
        "pendingReferrals": len([r for r in referrals if r["status"] == "pending"]),
        "dueFollowUps": len([f for f in follow_ups if f["status"] in ("due", "overdue")]),
        "recentCases": sorted(cases, key=lambda c: c["updatedAt"], reverse=True)[:5],
    }


# NOTE: submit-referral and upload-image MUST come before /{case_id} to avoid
# FastAPI treating the literal strings as a case_id path parameter.
@router.post("/submit-referral")
def submit_referral(payload: dict, user: Annotated[dict, Depends(get_current_user)], tenant_id: Annotated[str, Depends(require_tenant)]):
    """Mobile-friendly combined endpoint: create patient (optional) + case + referral.

    AI workflow: runs Gemini image quality checks on every submitted image BEFORE
    proceeding to AI skin assessment. If any image is rated poor or scores <60,
    skin assessment is skipped and the case is flagged for image retake.
    """
    patient_id = payload.get("patientId")
    patient = None
    if not patient_id and payload.get("patient"):
        p = store.add_patient(tenant_id, payload["patient"], user["id"])
        patient_id = p["id"]
        patient = p
    if not patient_id:
        raise HTTPException(status_code=400, detail="Patient required")
    clinical = payload.get("clinical", {})
    images = payload.get("images", [])
    case = store.add_case(tenant_id, {
        "patientId": patient_id,
        "primaryConcern": clinical.get("primaryConcern", ""),
        "clinicalInfo": clinical.get("clinicalInfo", ""),
        "durationDays": clinical.get("durationDays", 0),
        "suspectedCondition": clinical.get("suspectedCondition", "Awaiting specialist review"),
        "priority": clinical.get("priority", "routine"),
        "bodySite": clinical.get("bodySite"),
        "previousTreatment": clinical.get("previousTreatment"),
        "redFlags": clinical.get("redFlags", []),
        "symptoms": clinical.get("symptoms", []),
        "severity": clinical.get("severity"),
        "images": images,
    }, user["id"])
    tenant = store.get_tenant(tenant_id)
    if patient is None:
        patient = next((p for p in store.scope(tenant_id, "patients") if p["id"] == patient_id), None)
    referral = store.add_referral(tenant_id, {
        "ref": case["ref"],
        "caseId": case["id"],
        "patientName": patient["fullName"] if patient else "Patient",
        "fromClinic": tenant["name"] if tenant else "Village clinic",
        "status": "pending",
        "priority": case["priority"],
    })
    draft_id = payload.get("draftId")
    if draft_id:
        store.delete_draft(user["id"], draft_id)

    # Auto-assign to the least-loaded specialist — honour explicit specialistId if sent
    explicit_specialist = payload.get("specialistId") or clinical.get("specialistId")
    if explicit_specialist:
        store.update_case(case["id"], {"specialistId": explicit_specialist})
    else:
        store.auto_assign_specialist(case["id"], tenant_id)

    # Launch AI quality check & assessment in a background thread for instant response (< 300ms)
    import threading
    def _async_ai_task(c_dict, p_dict, t_id):
        try:
            _trigger_ai_workflow_for_case(c_dict, p_dict, t_id)
        except Exception as exc:
            import logging
            logging.getLogger(__name__).error("Async AI task error: %s", exc)

    threading.Thread(target=_async_ai_task, args=(case, patient, tenant_id), daemon=True).start()

    refreshed_case = next((c for c in store.scope(tenant_id, "cases") if c["id"] == case["id"]), case)

    return {
        "case": refreshed_case,
        "referral": referral,
        "patientId": patient_id,
        "ai": {"qualitySummary": None, "aiAssessmentRan": False, "status": "queued"},
    }


@router.post("/upload-image")
async def upload_image(
    user: Annotated[dict, Depends(get_current_user)],
    file: UploadFile = File(...),
):
    os.makedirs(settings.upload_dir, exist_ok=True)
    ext = os.path.splitext(file.filename or "photo.jpg")[1] or ".jpg"
    name = f"{uuid.uuid4().hex}{ext}"
    path = os.path.join(settings.upload_dir, name)
    content = await file.read()
    with open(path, "wb") as f:
        f.write(content)
    return {"url": f"/uploads/{name}", "filename": name}


@router.get("/{case_id}")
def get_case(
    case_id: str,
    user: Annotated[dict, Depends(get_current_user)],
    tenant_id: Annotated[str | None, Depends(get_effective_tenant_id)],
):
    case = next((c for c in _list_cases(user, tenant_id) if c["id"] == case_id), None)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    # Auto-assign + auto set in_review when a specialist opens a new case
    if user["role"] == "specialist":
        patch: dict[str, Any] = {}
        if not case.get("specialistId"):
            patch["specialistId"] = user["id"]
        if case.get("status") == "new":
            patch["status"] = "in_review"
            if not case.get("specialistId"):
                patch["specialistId"] = user["id"]
        if patch:
            updated = store.update_case(case_id, patch)
            if updated:
                case = updated

    return case


@router.post("")
def create_case(body: CaseCreate, user: Annotated[dict, Depends(get_current_user)], tenant_id: Annotated[str, Depends(require_tenant)]):
    case = store.add_case(tenant_id, body.model_dump(), user["id"])
    tenant = store.get_tenant(tenant_id)
    patient = next((p for p in store.scope(tenant_id, "patients") if p["id"] == body.patientId), None)
    store.add_referral(tenant_id, {
        "ref": case["ref"],
        "caseId": case["id"],
        "patientName": patient["fullName"] if patient else "Patient",
        "fromClinic": tenant["name"] if tenant else "Village clinic",
        "status": "pending",
        "priority": body.priority,
    })

    # Auto-assign to the least-loaded specialist
    store.auto_assign_specialist(case["id"], tenant_id)

    import threading
    def _async_ai_task_create(c_dict, p_dict, t_id):
        try:
            _trigger_ai_workflow_for_case(c_dict, p_dict, t_id)
        except Exception:
            pass

    threading.Thread(target=_async_ai_task_create, args=(case, patient, tenant_id), daemon=True).start()

    refreshed_case = next((c for c in store.scope(tenant_id, "cases") if c["id"] == case["id"]), case)
    return {
        "case": refreshed_case,
        "ai": {"qualitySummary": None, "aiAssessmentRan": False, "status": "queued"},
    }


@router.patch("/{case_id}")
def update_case(case_id: str, body: CaseUpdate, user: Annotated[dict, Depends(get_current_user)]):
    patch = {k: v for k, v in body.model_dump().items() if v is not None}
    from datetime import datetime, timezone

    # When treatment plan is submitted, translate into patient language & update referral
    if patch.get("treatmentPlan") or patch.get("status") == "reviewed":
        case = next((c for c in store.db.get("cases", []) if c["id"] == case_id), None)
        target_lang = "Swahili"
        if case:
            patient = next((p for p in store.db.get("patients", []) if p["id"] == case.get("patientId")), None)
            if patient and patient.get("language"):
                target_lang = patient.get("language")
            for ref in store.db.get("referrals", []):
                if ref.get("caseId") == case_id and ref.get("status") != "responded":
                    store.update_referral(ref["id"], {
                        "status": "responded",
                        "respondedAt": datetime.now(timezone.utc).isoformat(),
                    })
                    break

        if patch.get("treatmentPlan"):
            patch["treatmentPlan"] = gemini_service.translate_treatment_plan(patch["treatmentPlan"], target_lang)

    # When follow-up report is submitted, translate feedback and sync into followUps collection
    if patch.get("followUpReport") or patch.get("status") == "follow_up":
        case = next((c for c in store.db.get("cases", []) if c["id"] == case_id), None)
        existing_report = (case.get("followUpReport") or {}) if case else {}
        patch_report = patch.get("followUpReport") or {}
        report = {**existing_report, **patch_report}

        if report.get("specialistFeedback"):
            report["specialistFeedbackSwahili"] = gemini_service.translate_clinical_text(
                report["specialistFeedback"], "Swahili", "specialist feedback"
            )

        if patch.get("followUpReport"):
            patch["followUpReport"] = report

        tenant_id = (case.get("tenantId") if case else None) or user.get("tenantId")
        if tenant_id:
            follow_up = next((f for f in store.db.get("followUps", []) if f.get("caseId") == case_id), None)
            resp = report.get("response", "recorded")
            adh = report.get("adherence", "full")
            sym = report.get("symptoms", "")
            summary = f"Response: {resp} | Adherence: {adh}\n{sym}".strip()
            if report.get("worsening"):
                summary += "\n⚠ RED FLAG: Deterioration flagged for urgent re-triage"
            if report.get("specialistFeedback"):
                summary += f"\nSpecialist Feedback: {report.get('specialistFeedback')}"

            fu_status = "completed" if report.get("specialistAction") in ("discharge", "continue", "adjust_regimen", "escalate") else "due"

            if follow_up:
                store.update_follow_up(follow_up["id"], {
                    "status": fu_status,
                    "outcome": summary,
                    "followUpReport": report,
                })
            else:
                patient_name = report.get("submittedByName", "Patient")
                if case:
                    patient = next((p for p in store.db.get("patients", []) if p["id"] == case.get("patientId")), None)
                    if patient:
                        patient_name = patient.get("fullName", patient_name)
                store.add_follow_up(tenant_id, {
                    "caseId": case_id,
                    "caseRef": case.get("ref", f"REF-{case_id}") if case else f"REF-{case_id}",
                    "patientName": patient_name,
                    "scheduledFor": report.get("submittedAt", datetime.now(timezone.utc).isoformat()),
                    "purpose": f"Follow-Up Review ({resp})",
                    "status": fu_status,
                    "outcome": summary,
                    "followUpReport": report,
                })

    updated = store.update_case(case_id, patch)
    if not updated:
        raise HTTPException(status_code=404, detail="Case not found")
    return updated


@router.post("/{case_id}/notes")
def add_note(case_id: str, body: CaseNoteCreate, user: Annotated[dict, Depends(get_current_user)]):
    translated_body = gemini_service.translate_clinical_text(
        body.body, "Swahili", f"{user.get('role', 'user')} note"
    )
    note_text = body.body
    if translated_body and translated_body != body.body:
        note_text = f"{body.body}\n\n[Swahili Translation]: {translated_body}"

    updated = store.add_case_note(case_id, user, note_text)
    if not updated:
        raise HTTPException(status_code=404, detail="Case not found")
    return updated
