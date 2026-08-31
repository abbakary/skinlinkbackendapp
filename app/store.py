"""SQLAlchemy-backed database store mirroring the Next.js data-store contract."""

from __future__ import annotations

import uuid
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Optional
from passlib.context import CryptContext
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import settings
from app.media import expand_media_urls, normalize_stored_media_url
from app.database import (
    SessionLocal,
    TenantModel,
    UserModel,
    PatientModel,
    DermCaseModel,
    ReferralModel,
    FollowUpModel,
    ResourceModel,
    DraftModel,
    ApplicationModel,
    ApiKeyApplicationModel,
    ApiKeyModel,
    AiAuditTrailModel,
    SpecialistReviewModel,
    init_db,
)
from app.seed import seed_db, DEMO_ORG_PASSWORD, DEMO_PLATFORM_PASSWORD

pwd_context = CryptContext(schemes=["bcrypt", "pbkdf2_sha256"], deprecated="auto")


def _safe_hash(password: str) -> str:
    pwd_bytes = password.encode("utf-8")[:72]
    safe_pwd = pwd_bytes.decode("utf-8", errors="ignore")
    try:
        return pwd_context.hash(safe_pwd)
    except Exception:
        import hashlib
        return "sha256$" + hashlib.sha256(safe_pwd.encode("utf-8")).hexdigest()


def _safe_verify(password: str, hashed: str) -> bool:
    pwd_bytes = password.encode("utf-8")[:72]
    safe_pwd = pwd_bytes.decode("utf-8", errors="ignore")
    if hashed.startswith("sha256$"):
        import hashlib
        return hashed == "sha256$" + hashlib.sha256(safe_pwd.encode("utf-8")).hexdigest()
    try:
        return pwd_context.verify(safe_pwd, hashed)
    except Exception:
        return False



def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _uid(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


def _normalize_image_url(url: str) -> str:
    return normalize_stored_media_url(url)


def _model_to_dict(obj: Any) -> Optional[dict[str, Any]]:
    if obj is None:
        return None
    if isinstance(obj, TenantModel):
        return {
            "id": obj.id,
            "name": obj.name,
            "slug": obj.slug,
            "plan": obj.plan,
            "status": obj.status,
            "country": obj.country,
            "region": obj.region,
            "district": obj.district,
            "facilityRegNumber": obj.facilityRegNumber,
            "facilityType": obj.facilityType,
            "contactName": obj.contactName,
            "contactEmail": obj.contactEmail,
            "contactPhone": obj.contactPhone,
            "dpo": obj.dpo,
            "seats": obj.seats,
            "usedSeats": obj.usedSeats,
            "clinics": obj.clinics,
            "createdAt": obj.createdAt,
            "primaryColor": obj.primaryColor,
            "messages": obj.messages or [],
        }
    elif isinstance(obj, UserModel):
        return expand_media_urls({
            "id": obj.id,
            "tenantId": obj.tenantId,
            "name": obj.name,
            "email": obj.email,
            "role": obj.role,
            "title": obj.title,
            "specialty": obj.specialty,
            "phone": obj.phone,
            "status": obj.status,
            "avatarColor": obj.avatarColor,
            "lastActive": obj.lastActive,
            "createdAt": obj.createdAt,
            "verificationLevel": obj.verificationLevel,
            "nidaNumber": obj.nidaNumber,
            "passportPhotoUrl": obj.passportPhotoUrl,
            "mctRegistrationNumber": obj.mctRegistrationNumber,
            "tnmcRegistrationNumber": obj.tnmcRegistrationNumber,
            "licenceNumber": obj.licenceNumber,
            "licenceExpiry": obj.licenceExpiry,
            "licenceStatus": obj.licenceStatus,
            "specialistQualification": obj.specialistQualification,
            "practiceName": obj.practiceName,
            "facilityRegNumber": obj.facilityRegNumber,
            "indemnityInsurer": obj.indemnityInsurer,
            "indemnityPolicyNumber": obj.indemnityPolicyNumber,
            "indemnityExpiry": obj.indemnityExpiry,
            "documents": obj.documents or [],
        })
    elif isinstance(obj, PatientModel):
        return {
            "id": obj.id,
            "tenantId": obj.tenantId,
            "code": obj.code,
            "fullName": obj.fullName,
            "age": obj.age,
            "gender": obj.gender,
            "phone": obj.phone,
            "alternatePhone": obj.alternatePhone,
            "village": obj.village,
            "region": obj.region,
            "district": obj.district,
            "country": obj.country,
            "medicalHistory": obj.medicalHistory,
            "allergies": obj.allergies,
            "currentMedications": obj.currentMedications,
            "chronicConditions": obj.chronicConditions,
            "preferredLanguage": obj.preferredLanguage,
            "consentObtained": obj.consentObtained,
            "consentDate": obj.consentDate,
            "consentWitness": obj.consentWitness,
            "consentForPhotography": obj.consentForPhotography,
            "consentForRemoteReview": obj.consentForRemoteReview,
            "consentForStorage": obj.consentForStorage,
            "registeredById": obj.registeredById,
            "createdAt": obj.createdAt,
            "notes": obj.notes,
        }
    elif isinstance(obj, DermCaseModel):
        return expand_media_urls({
            "id": obj.id,
            "tenantId": obj.tenantId,
            "ref": obj.ref,
            "patientId": obj.patientId,
            "clinicianId": obj.clinicianId,
            "specialistId": obj.specialistId,
            "primaryConcern": obj.primaryConcern,
            "clinicalInfo": obj.clinicalInfo,
            "durationDays": obj.durationDays,
            "suspectedCondition": obj.suspectedCondition,
            "bodySite": obj.bodySite,
            "previousTreatment": obj.previousTreatment,
            "redFlags": obj.redFlags or [],
            "symptoms": obj.symptoms or [],
            "severity": obj.severity,
            "status": obj.status,
            "priority": obj.priority,
            "images": obj.images or [],
            "ai": obj.ai,
            "aiImageQuality": obj.aiImageQuality,
            "imageQualityStatus": obj.imageQualityStatus,
            "treatmentPlan": obj.treatmentPlan,
            "followUpReport": obj.followUpReport,
            "notes": obj.notes or [],
            "createdAt": obj.createdAt,
            "updatedAt": obj.updatedAt,
        })
    elif isinstance(obj, ReferralModel):
        return {
            "id": obj.id,
            "tenantId": obj.tenantId,
            "ref": obj.ref,
            "caseId": obj.caseId,
            "patientName": obj.patientName,
            "fromClinic": obj.fromClinic,
            "toSpecialistId": obj.toSpecialistId,
            "status": obj.status,
            "priority": obj.priority,
            "createdAt": obj.createdAt,
            "respondedAt": obj.respondedAt,
        }
    elif isinstance(obj, FollowUpModel):
        return {
            "id": obj.id,
            "tenantId": obj.tenantId,
            "caseId": obj.caseId,
            "caseRef": obj.caseRef,
            "patientName": obj.patientName,
            "scheduledFor": obj.scheduledFor,
            "status": obj.status,
            "assignedToId": obj.assignedToId,
            "purpose": obj.purpose,
            "outcome": obj.outcome,
            "followUpReport": obj.followUpReport,
        }
    elif isinstance(obj, ResourceModel):
        return {
            "id": obj.id,
            "tenantId": obj.tenantId,
            "title": obj.title,
            "category": obj.category,
            "type": obj.type,
            "description": obj.description,
            "updatedAt": obj.updatedAt,
        }
    elif isinstance(obj, DraftModel):
        return expand_media_urls({"id": obj.id, "userId": obj.userId, "updatedAt": obj.updatedAt, **(obj.data or {})})
    elif isinstance(obj, ApplicationModel):
        return expand_media_urls({
            "id": obj.id,
            "applicationType": obj.applicationType,
            "status": obj.status,
            "verificationLevel": obj.verificationLevel,
            "submittedAt": obj.submittedAt,
            "reviewedAt": obj.reviewedAt,
            "reviewedBy": obj.reviewedBy,
            "reviewNotes": obj.reviewNotes,
            "verifiedItems": obj.verifiedItems or [],
            **(obj.data or {}),
        })
    elif isinstance(obj, ApiKeyApplicationModel):
        return {
            "id": obj.id,
            "status": obj.status,
            "submittedAt": obj.submittedAt,
            **(obj.data or {}),
        }
    elif isinstance(obj, ApiKeyModel):
        return {
            "id": obj.id,
            "keyHash": obj.keyHash,
            "createdAt": obj.createdAt,
            **(obj.data or {}),
        }
    elif isinstance(obj, AiAuditTrailModel):
        return {
            "id": obj.id,
            "caseId": obj.caseId,
            "requestType": obj.requestType,
            "aiModel": obj.aiModel,
            "requestTimestamp": obj.requestTimestamp,
            "imageIds": obj.imageIds or [],
            "clinicalInput": obj.clinicalInput,
            "clinicalInputVersion": obj.clinicalInputVersion,
            "aiOutput": obj.aiOutput,
            "createdAt": obj.createdAt,
        }
    elif isinstance(obj, SpecialistReviewModel):
        result = {
            "id": obj.id,
            "caseId": obj.caseId,
            "specialistId": obj.specialistId,
            "finalDecisionTimestamp": obj.finalDecisionTimestamp,
            "finalAssessment": obj.finalAssessment,
            "finalCondition": obj.finalCondition,
            "clinicalAction": obj.clinicalAction,
            "treatmentGuidance": obj.treatmentGuidance,
            "followUpPeriodWeeks": obj.followUpPeriodWeeks,
            "specialistNotes": obj.specialistNotes,
            "confirmsAiAssessment": obj.confirmsAiAssessment,
            "partialEndorsement": obj.partialEndorsement,
            **(obj.data or {}),
        }
        return expand_media_urls(result)
    return None


class DBProxy:
    def __init__(self, store: 'DatabaseStore'):
        self._store = store

    def get(self, collection: str, default=None):
        res = self._store.scope(None, collection)
        return res if res is not None else default

    def __getitem__(self, collection: str):
        return self._store.scope(None, collection)


class DatabaseStore:
    def __init__(self) -> None:
        init_db()
        seed_db()
        self.db = DBProxy(self)

    def verify_password(self, email: str, password: str) -> bool:
        session = SessionLocal()
        try:
            user = session.query(UserModel).filter(func.lower(UserModel.email) == email.lower()).first()
            if not user:
                return False
            if user.passwordHash:
                if user.passwordHash.startswith("$2") or user.passwordHash.startswith("sha256$"):
                    return _safe_verify(password, user.passwordHash)
                return user.passwordHash == password
            # Default password fallback
            if user.role == "platform_admin":
                return password in (settings.platform_admin_password, DEMO_PLATFORM_PASSWORD)
            return password == DEMO_ORG_PASSWORD
        finally:
            session.close()

    def get_user_by_email(self, email: str) -> Optional[dict[str, Any]]:
        session = SessionLocal()
        try:
            user = session.query(UserModel).filter(func.lower(UserModel.email) == email.lower()).first()
            return _model_to_dict(user)
        finally:
            session.close()

    def get_user(self, user_id: str) -> Optional[dict[str, Any]]:
        session = SessionLocal()
        try:
            user = session.query(UserModel).filter(UserModel.id == user_id).first()
            return _model_to_dict(user)
        finally:
            session.close()

    def get_tenant(self, tenant_id: str) -> Optional[dict[str, Any]]:
        session = SessionLocal()
        try:
            tenant = session.query(TenantModel).filter(TenantModel.id == tenant_id).first()
            return _model_to_dict(tenant)
        finally:
            session.close()

    def scope(self, tenant_id: Optional[str], collection: str) -> list[dict[str, Any]]:
        session = SessionLocal()
        try:
            model_map = {
                "tenants": TenantModel,
                "users": UserModel,
                "patients": PatientModel,
                "cases": DermCaseModel,
                "referrals": ReferralModel,
                "followUps": FollowUpModel,
                "resources": ResourceModel,
                "drafts": DraftModel,
                "applications": ApplicationModel,
                "apiKeyApplications": ApiKeyApplicationModel,
                "apiKeys": ApiKeyModel,
                "aiAuditTrail": AiAuditTrailModel,
                "specialistReviews": SpecialistReviewModel,
            }
            cls = model_map.get(collection)
            if not cls:
                return []
            query = session.query(cls)
            if tenant_id is not None and hasattr(cls, "tenantId"):
                query = query.filter(getattr(cls, "tenantId") == tenant_id)
            items = query.all()
            return [_model_to_dict(i) for i in items]
        finally:
            session.close()

    def next_patient_code(self, tenant_id: str) -> str:
        session = SessionLocal()
        try:
            codes = [p.code for p in session.query(PatientModel).filter(PatientModel.tenantId == tenant_id).all()]
            nums = []
            for c in codes:
                try:
                    nums.append(int(c.split("-")[-1]))
                except ValueError:
                    pass
            n = max(nums, default=0) + 1
            return f"PT-{n:04d}"
        finally:
            session.close()

    def add_patient(self, tenant_id: str, data: dict[str, Any], registered_by: str) -> dict[str, Any]:
        session = SessionLocal()
        try:
            patient_id = _uid("p")
            code = self.next_patient_code(tenant_id)
            iso = _now_iso()
            obj = PatientModel(
                id=patient_id,
                tenantId=tenant_id,
                code=code,
                fullName=data["fullName"],
                age=data["age"],
                gender=data["gender"],
                phone=data.get("phone"),
                alternatePhone=data.get("alternatePhone"),
                village=data["village"],
                region=data.get("region"),
                district=data.get("district"),
                country=data.get("country"),
                medicalHistory=data.get("medicalHistory"),
                allergies=data.get("allergies"),
                currentMedications=data.get("currentMedications"),
                chronicConditions=data.get("chronicConditions"),
                preferredLanguage=data.get("preferredLanguage"),
                consentObtained=data.get("consentObtained", False),
                consentDate=data.get("consentDate"),
                consentWitness=data.get("consentWitness"),
                consentForPhotography=data.get("consentForPhotography", False),
                consentForRemoteReview=data.get("consentForRemoteReview", False),
                consentForStorage=data.get("consentForStorage", False),
                registeredById=registered_by,
                createdAt=iso,
                notes=data.get("notes"),
            )
            session.add(obj)
            session.commit()
            session.refresh(obj)
            return _model_to_dict(obj)
        finally:
            session.close()

    def update_patient(self, patient_id: str, patch: dict[str, Any]) -> Optional[dict[str, Any]]:
        session = SessionLocal()
        try:
            obj = session.query(PatientModel).filter(PatientModel.id == patient_id).first()
            if not obj:
                return None
            for k, v in patch.items():
                if hasattr(obj, k):
                    setattr(obj, k, v)
            session.commit()
            session.refresh(obj)
            return _model_to_dict(obj)
        finally:
            session.close()

    def add_case(self, tenant_id: str, data: dict[str, Any], clinician_id: str) -> dict[str, Any]:
        session = SessionLocal()
        try:
            case_count = session.query(DermCaseModel).count()
            ref = data.get("ref") or f"REF-{datetime.now().year}-{1000 + case_count}"
            iso = _now_iso()
            images = []
            for idx, img in enumerate(data.get("images", [])):
                quality_rating = img.get("quality") or "acceptable"
                quality_score = img.get("qualityScore") or img.get("quality_score") or 75
                images.append({
                    "id": _uid("img"),
                    "url": _normalize_image_url(img["url"]),
                    "angle": img.get("angle", "Overview"),
                    "quality": quality_rating,
                    "qualityScore": quality_score,
                    "qualityNotes": img.get("qualityNotes"),
                    "capturedAt": img.get("capturedAt", iso),
                })
            obj = DermCaseModel(
                id=_uid("c"),
                tenantId=tenant_id,
                ref=ref,
                patientId=data["patientId"],
                clinicianId=clinician_id,
                specialistId=data.get("specialistId"),
                primaryConcern=data["primaryConcern"],
                clinicalInfo=data.get("clinicalInfo", data["primaryConcern"]),
                durationDays=data.get("durationDays", 0),
                suspectedCondition=data.get("suspectedCondition", "Awaiting specialist review"),
                bodySite=data.get("bodySite"),
                previousTreatment=data.get("previousTreatment"),
                redFlags=data.get("redFlags", []),
                symptoms=data.get("symptoms", []),
                severity=data.get("severity"),
                status=data.get("status", "new"),
                priority=data.get("priority", "routine"),
                images=images,
                notes=[],
                createdAt=iso,
                updatedAt=iso,
                treatmentPlan=data.get("treatmentPlan"),
            )
            session.add(obj)
            session.commit()
            session.refresh(obj)
            return _model_to_dict(obj)
        finally:
            session.close()

    def update_case(self, case_id: str, patch: dict[str, Any]) -> Optional[dict[str, Any]]:
        session = SessionLocal()
        try:
            obj = session.query(DermCaseModel).filter(DermCaseModel.id == case_id).first()
            if not obj:
                return None
            if "images" in patch and isinstance(patch["images"], list):
                for img in patch["images"]:
                    if isinstance(img, dict) and img.get("url"):
                        img["url"] = _normalize_image_url(img["url"])
            for k, v in patch.items():
                if hasattr(obj, k):
                    setattr(obj, k, v)
            obj.updatedAt = _now_iso()
            session.commit()
            session.refresh(obj)
            return _model_to_dict(obj)
        finally:
            session.close()

    def add_case_note(self, case_id: str, author: dict[str, Any], body: str) -> Optional[dict[str, Any]]:
        session = SessionLocal()
        try:
            obj = session.query(DermCaseModel).filter(DermCaseModel.id == case_id).first()
            if not obj:
                return None
            note = {
                "id": _uid("n"),
                "authorId": author["id"],
                "authorName": author["name"],
                "body": body,
                "createdAt": _now_iso(),
            }
            notes = list(obj.notes or [])
            notes.append(note)
            obj.notes = notes
            obj.updatedAt = _now_iso()
            session.commit()
            session.refresh(obj)
            return _model_to_dict(obj)
        finally:
            session.close()

    def add_referral(self, tenant_id: str, data: dict[str, Any]) -> dict[str, Any]:
        session = SessionLocal()
        try:
            if data.get("caseId"):
                existing = session.query(ReferralModel).filter(ReferralModel.caseId == data["caseId"]).first()
                if existing:
                    return _model_to_dict(existing)
            obj = ReferralModel(
                id=_uid("r"),
                tenantId=tenant_id,
                ref=data["ref"],
                caseId=data["caseId"],
                patientName=data["patientName"],
                fromClinic=data["fromClinic"],
                toSpecialistId=data.get("toSpecialistId"),
                status=data.get("status", "pending"),
                priority=data.get("priority", "routine"),
                createdAt=_now_iso(),
                respondedAt=data.get("respondedAt"),
            )
            session.add(obj)
            session.commit()
            session.refresh(obj)
            return _model_to_dict(obj)
        finally:
            session.close()

    def add_follow_up(self, tenant_id: str, data: dict[str, Any]) -> dict[str, Any]:
        session = SessionLocal()
        try:
            obj = FollowUpModel(
                id=_uid("f"),
                tenantId=tenant_id,
                caseId=data["caseId"],
                caseRef=data["caseRef"],
                patientName=data["patientName"],
                scheduledFor=data["scheduledFor"],
                status=data.get("status", "scheduled"),
                assignedToId=data.get("assignedToId"),
                purpose=data["purpose"],
                outcome=data.get("outcome"),
                followUpReport=data.get("followUpReport"),
            )
            session.add(obj)
            session.commit()
            session.refresh(obj)
            return _model_to_dict(obj)
        finally:
            session.close()

    def update_follow_up(self, follow_up_id: str, patch: dict[str, Any]) -> Optional[dict[str, Any]]:
        session = SessionLocal()
        try:
            obj = session.query(FollowUpModel).filter(FollowUpModel.id == follow_up_id).first()
            if not obj:
                return None
            for k, v in patch.items():
                if hasattr(obj, k):
                    setattr(obj, k, v)
            session.commit()
            session.refresh(obj)
            return _model_to_dict(obj)
        finally:
            session.close()

    def add_tenant_message(self, tenant_id: str, msg: dict[str, Any]) -> None:
        session = SessionLocal()
        try:
            obj = session.query(TenantModel).filter(TenantModel.id == tenant_id).first()
            if obj:
                msgs = list(obj.messages or [])
                msgs.insert(0, msg)
                obj.messages = msgs
                session.commit()
        finally:
            session.close()

    def update_referral(self, referral_id: str, patch: dict[str, Any]) -> Optional[dict[str, Any]]:
        session = SessionLocal()
        try:
            obj = session.query(ReferralModel).filter(ReferralModel.id == referral_id).first()
            if not obj:
                return None
            for k, v in patch.items():
                if hasattr(obj, k):
                    setattr(obj, k, v)
            session.commit()
            session.refresh(obj)
            return _model_to_dict(obj)
        finally:
            session.close()

    def add_resource(self, tenant_id: str, data: dict[str, Any]) -> dict[str, Any]:
        session = SessionLocal()
        try:
            obj = ResourceModel(
                id=_uid("res"),
                tenantId=tenant_id,
                title=data["title"],
                category=data["category"],
                type=data["type"],
                description=data["description"],
                updatedAt=_now_iso(),
            )
            session.add(obj)
            session.commit()
            session.refresh(obj)
            return _model_to_dict(obj)
        finally:
            session.close()

    def add_tenant(self, data: dict[str, Any]) -> dict[str, Any]:
        session = SessionLocal()
        try:
            obj = TenantModel(
                id=_uid("t"),
                name=data["name"],
                slug=data["slug"],
                plan=data.get("plan", "pilot"),
                status=data.get("status", "active"),
                country=data["country"],
                region=data["region"],
                district=data.get("district"),
                facilityRegNumber=data.get("facilityRegNumber"),
                facilityType=data.get("facilityType"),
                contactName=data["contactName"],
                contactEmail=data["contactEmail"],
                contactPhone=data.get("contactPhone"),
                dpo=data.get("dpo"),
                seats=data.get("seats", 10),
                usedSeats=data.get("usedSeats", 0),
                clinics=data.get("clinics", 1),
                createdAt=_now_iso(),
                primaryColor=data.get("primaryColor", "#1f7a8c"),
                messages=[],
            )
            session.add(obj)
            session.commit()
            session.refresh(obj)
            return _model_to_dict(obj)
        finally:
            session.close()

    def update_tenant(self, tenant_id: str, patch: dict[str, Any]) -> Optional[dict[str, Any]]:
        session = SessionLocal()
        try:
            obj = session.query(TenantModel).filter(TenantModel.id == tenant_id).first()
            if not obj:
                return None
            for k, v in patch.items():
                if hasattr(obj, k):
                    setattr(obj, k, v)
            session.commit()
            session.refresh(obj)
            return _model_to_dict(obj)
        finally:
            session.close()

    def create_tenant_account(self, data: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
        slug = data["name"].lower().replace(" ", "-").replace("_", "-")
        slug = "".join(c for c in slug if c.isalnum() or c == "-").strip("-")[:40]
        tenant = self.add_tenant({
            "name": data["name"],
            "slug": slug,
            "plan": data.get("plan", "pilot"),
            "status": "active",
            "country": data["country"],
            "region": data["region"],
            "contactName": data["adminName"],
            "contactEmail": data["adminEmail"],
            "seats": data.get("seats", 10),
            "clinics": data.get("clinics", 1),
            "primaryColor": data.get("primaryColor") or "#1f7a8c",
        })
        admin = self.add_user({
            "tenantId": tenant["id"],
            "name": data["adminName"],
            "email": data["adminEmail"],
            "role": "org_admin",
            "title": data.get("adminTitle") or "Organization Administrator",
            "phone": data.get("adminPhone"),
            "status": "active",
            "avatarColor": data.get("primaryColor") or "#1f7a8c",
        }, data["adminPassword"])
        self.update_tenant(tenant["id"], {"usedSeats": 1})
        tenant = self.get_tenant(tenant["id"]) or tenant
        return tenant, admin

    def add_user(self, data: dict[str, Any], password: str) -> dict[str, Any]:
        session = SessionLocal()
        try:
            iso = _now_iso()
            password_hash = _safe_hash(password)
            obj = UserModel(
                id=_uid("u"),
                tenantId=data.get("tenantId"),
                name=data["name"],
                email=data["email"],
                passwordHash=password_hash,
                role=data["role"],
                title=data.get("title"),
                specialty=data.get("specialty"),
                phone=data.get("phone"),
                status=data.get("status", "active"),
                avatarColor=data.get("avatarColor", "#0c2340"),
                lastActive=iso,
                createdAt=iso,
                verificationLevel=data.get("verificationLevel", 0),
                nidaNumber=data.get("nidaNumber"),
                passportPhotoUrl=data.get("passportPhotoUrl"),
                mctRegistrationNumber=data.get("mctRegistrationNumber"),
                tnmcRegistrationNumber=data.get("tnmcRegistrationNumber"),
                licenceNumber=data.get("licenceNumber"),
                licenceExpiry=data.get("licenceExpiry"),
                licenceStatus=data.get("licenceStatus"),
                specialistQualification=data.get("specialistQualification"),
                practiceName=data.get("practiceName"),
                facilityRegNumber=data.get("facilityRegNumber"),
                indemnityInsurer=data.get("indemnityInsurer"),
                indemnityPolicyNumber=data.get("indemnityPolicyNumber"),
                indemnityExpiry=data.get("indemnityExpiry"),
                documents=data.get("documents", []),
            )
            session.add(obj)
            session.commit()
            
            tenant_id = data.get("tenantId")
            if tenant_id:
                t_obj = session.query(TenantModel).filter(TenantModel.id == tenant_id).first()
                if t_obj:
                    t_obj.usedSeats = (t_obj.usedSeats or 0) + 1
                    session.commit()

            session.refresh(obj)
            return _model_to_dict(obj)
        finally:
            session.close()

    def update_user(self, user_id: str, patch: dict[str, Any]) -> Optional[dict[str, Any]]:
        session = SessionLocal()
        try:
            obj = session.query(UserModel).filter(UserModel.id == user_id).first()
            if not obj:
                return None
            for k, v in patch.items():
                if hasattr(obj, k):
                    setattr(obj, k, v)
            obj.lastActive = _now_iso()
            session.commit()
            session.refresh(obj)
            return _model_to_dict(obj)
        finally:
            session.close()

    def set_password(self, email: str, password: str) -> None:
        session = SessionLocal()
        try:
            obj = session.query(UserModel).filter(func.lower(UserModel.email) == email.lower()).first()
            if obj:
                obj.passwordHash = _safe_hash(password)
                session.commit()
        finally:
            session.close()

    def delete_user(self, user_id: str) -> None:
        session = SessionLocal()
        try:
            obj = session.query(UserModel).filter(UserModel.id == user_id).first()
            if not obj:
                return
            tenant_id = obj.tenantId
            session.delete(obj)
            if tenant_id:
                t_obj = session.query(TenantModel).filter(TenantModel.id == tenant_id).first()
                if t_obj:
                    t_obj.usedSeats = max(0, (t_obj.usedSeats or 1) - 1)
            session.commit()
        finally:
            session.close()

    def delete_tenant(self, tenant_id: str) -> None:
        session = SessionLocal()
        try:
            t_obj = session.query(TenantModel).filter(TenantModel.id == tenant_id).first()
            if t_obj:
                session.delete(t_obj)
                session.query(UserModel).filter(UserModel.tenantId == tenant_id).delete()
                session.query(PatientModel).filter(PatientModel.tenantId == tenant_id).delete()
                session.query(DermCaseModel).filter(DermCaseModel.tenantId == tenant_id).delete()
                session.query(ReferralModel).filter(ReferralModel.tenantId == tenant_id).delete()
                session.query(FollowUpModel).filter(FollowUpModel.tenantId == tenant_id).delete()
                session.query(ResourceModel).filter(ResourceModel.tenantId == tenant_id).delete()
                session.commit()
        finally:
            session.close()

    def auto_assign_specialist(self, case_id: str, tenant_id: str) -> Optional[dict[str, Any]]:
        session = SessionLocal()
        try:
            specialists = session.query(UserModel).filter(
                UserModel.tenantId == tenant_id,
                UserModel.role == "specialist",
                UserModel.status == "active"
            ).all()
            if not specialists:
                return None
            open_statuses = {"new", "in_review"}
            cases = session.query(DermCaseModel).filter(
                DermCaseModel.tenantId == tenant_id,
                DermCaseModel.status.in_(open_statuses)
            ).all()
            case_counts: dict[str, int] = {s.id: 0 for s in specialists}
            for c in cases:
                if c.specialistId and c.specialistId in case_counts:
                    case_counts[c.specialistId] += 1

            chosen = min(specialists, key=lambda s: case_counts[s.id])
            case_obj = session.query(DermCaseModel).filter(DermCaseModel.id == case_id).first()
            if case_obj:
                case_obj.specialistId = chosen.id
                session.commit()
            return _model_to_dict(chosen)
        finally:
            session.close()

    def list_specialists(self, tenant_id: str) -> list[dict[str, Any]]:
        session = SessionLocal()
        try:
            specialists = session.query(UserModel).filter(
                UserModel.tenantId == tenant_id,
                UserModel.role == "specialist",
                UserModel.status == "active"
            ).all()
            open_statuses = {"new", "in_review"}
            cases = session.query(DermCaseModel).filter(
                DermCaseModel.tenantId == tenant_id,
                DermCaseModel.status.in_(open_statuses)
            ).all()
            result = []
            for s in specialists:
                open_cases = sum(1 for c in cases if c.specialistId == s.id)
                d = _model_to_dict(s)
                d["openCases"] = open_cases
                d["isBusy"] = open_cases > 3
                result.append(d)
            return result
        finally:
            session.close()

    def list_users(self, tenant_id: Optional[str] = None) -> list[dict[str, Any]]:
        session = SessionLocal()
        try:
            query = session.query(UserModel)
            if tenant_id is not None:
                query = query.filter(UserModel.tenantId == tenant_id)
            return [_model_to_dict(u) for u in query.all()]
        finally:
            session.close()

    def get_drafts(self, user_id: str) -> list[dict[str, Any]]:
        session = SessionLocal()
        try:
            drafts = session.query(DraftModel).filter(DraftModel.userId == user_id).order_by(DraftModel.updatedAt.desc()).all()
            return [_model_to_dict(d) for d in drafts]
        finally:
            session.close()

    def save_draft(self, user_id: str, draft: dict[str, Any]) -> dict[str, Any]:
        session = SessionLocal()
        try:
            draft_id = draft.get("id") or _uid("draft")
            iso = _now_iso()
            obj = session.query(DraftModel).filter(DraftModel.id == draft_id, DraftModel.userId == user_id).first()
            if obj:
                obj.data = {**draft, "id": draft_id}
                obj.updatedAt = iso
            else:
                obj = DraftModel(id=draft_id, userId=user_id, data={**draft, "id": draft_id}, updatedAt=iso)
                session.add(obj)
            session.commit()
            session.refresh(obj)
            return _model_to_dict(obj)
        finally:
            session.close()

    def delete_draft(self, user_id: str, draft_id: str) -> None:
        session = SessionLocal()
        try:
            session.query(DraftModel).filter(DraftModel.id == draft_id, DraftModel.userId == user_id).delete()
            session.commit()
        finally:
            session.close()

    # ── Applications ──────────────────────────────────────────────────────────

    def add_application(self, data: dict[str, Any]) -> dict[str, Any]:
        session = SessionLocal()
        try:
            app_id = _uid("app")
            iso = _now_iso()
            obj = ApplicationModel(
                id=app_id,
                applicationType=data.get("applicationType", "organization"),
                status="pending",
                verificationLevel=0,
                submittedAt=iso,
                data=data,
            )
            session.add(obj)
            session.commit()
            session.refresh(obj)
            return _model_to_dict(obj)
        finally:
            session.close()

    def list_applications(self, status: Optional[str] = None) -> list[dict[str, Any]]:
        session = SessionLocal()
        try:
            query = session.query(ApplicationModel)
            if status:
                query = query.filter(ApplicationModel.status == status)
            query = query.order_by(ApplicationModel.submittedAt.desc())
            return [_model_to_dict(a) for a in query.all()]
        finally:
            session.close()

    def get_application(self, app_id: str) -> Optional[dict[str, Any]]:
        session = SessionLocal()
        try:
            obj = session.query(ApplicationModel).filter(ApplicationModel.id == app_id).first()
            return _model_to_dict(obj)
        finally:
            session.close()

    def update_application(self, app_id: str, patch: dict[str, Any]) -> Optional[dict[str, Any]]:
        session = SessionLocal()
        try:
            obj = session.query(ApplicationModel).filter(ApplicationModel.id == app_id).first()
            if not obj:
                return None
            for k, v in patch.items():
                if hasattr(obj, k):
                    setattr(obj, k, v)
                else:
                    d = dict(obj.data or {})
                    d[k] = v
                    obj.data = d
            session.commit()
            session.refresh(obj)
            return _model_to_dict(obj)
        finally:
            session.close()

    # ── API Key Applications & Keys ───────────────────────────────────────────

    def add_api_key_application(self, data: dict[str, Any]) -> dict[str, Any]:
        session = SessionLocal()
        try:
            app_id = _uid("apik")
            iso = _now_iso()
            obj = ApiKeyApplicationModel(id=app_id, status="pending", submittedAt=iso, data=data)
            session.add(obj)
            session.commit()
            session.refresh(obj)
            return _model_to_dict(obj)
        finally:
            session.close()

    def list_api_key_applications(self, status: Optional[str] = None) -> list[dict[str, Any]]:
        session = SessionLocal()
        try:
            query = session.query(ApiKeyApplicationModel)
            if status:
                query = query.filter(ApiKeyApplicationModel.status == status)
            return [_model_to_dict(a) for a in query.all()]
        finally:
            session.close()

    def get_api_key_application(self, app_id: str) -> Optional[dict[str, Any]]:
        session = SessionLocal()
        try:
            obj = session.query(ApiKeyApplicationModel).filter(ApiKeyApplicationModel.id == app_id).first()
            return _model_to_dict(obj)
        finally:
            session.close()

    def update_api_key_application(self, app_id: str, patch: dict[str, Any]) -> Optional[dict[str, Any]]:
        session = SessionLocal()
        try:
            obj = session.query(ApiKeyApplicationModel).filter(ApiKeyApplicationModel.id == app_id).first()
            if not obj:
                return None
            for k, v in patch.items():
                if hasattr(obj, k):
                    setattr(obj, k, v)
                else:
                    d = dict(obj.data or {})
                    d[k] = v
                    obj.data = d
            session.commit()
            session.refresh(obj)
            return _model_to_dict(obj)
        finally:
            session.close()

    def add_api_key(self, data: dict[str, Any]) -> dict[str, Any]:
        session = SessionLocal()
        try:
            key_id = _uid("key")
            iso = _now_iso()
            key_hash = data.get("keyHash", "")
            obj = ApiKeyModel(id=key_id, keyHash=key_hash, createdAt=iso, data=data)
            session.add(obj)
            session.commit()
            session.refresh(obj)
            return _model_to_dict(obj)
        finally:
            session.close()

    def list_api_keys(self) -> list[dict[str, Any]]:
        session = SessionLocal()
        try:
            keys = session.query(ApiKeyModel).all()
            res = []
            for k in keys:
                d = _model_to_dict(k)
                d.pop("keyHash", None)
                res.append(d)
            return res
        finally:
            session.close()

    def get_api_key(self, key_id: str) -> Optional[dict[str, Any]]:
        session = SessionLocal()
        try:
            obj = session.query(ApiKeyModel).filter(ApiKeyModel.id == key_id).first()
            return _model_to_dict(obj)
        finally:
            session.close()

    def get_api_key_by_hash(self, key_hash: str) -> Optional[dict[str, Any]]:
        session = SessionLocal()
        try:
            obj = session.query(ApiKeyModel).filter(ApiKeyModel.keyHash == key_hash).first()
            return _model_to_dict(obj)
        finally:
            session.close()

    def update_api_key(self, key_id: str, patch: dict[str, Any]) -> Optional[dict[str, Any]]:
        session = SessionLocal()
        try:
            obj = session.query(ApiKeyModel).filter(ApiKeyModel.id == key_id).first()
            if not obj:
                return None
            for k, v in patch.items():
                if hasattr(obj, k):
                    setattr(obj, k, v)
                else:
                    d = dict(obj.data or {})
                    d[k] = v
                    obj.data = d
            session.commit()
            session.refresh(obj)
            return _model_to_dict(obj)
        finally:
            session.close()

    def add_ai_audit_trail(self, data: dict[str, Any]) -> dict[str, Any]:
        session = SessionLocal()
        try:
            iso = _now_iso()
            obj = AiAuditTrailModel(
                id=_uid("ai"),
                caseId=data.get("caseId"),
                requestType=data.get("requestType", "unknown"),
                aiModel=data.get("aiModel", "unknown"),
                requestTimestamp=data.get("requestTimestamp", iso),
                imageIds=data.get("imageIds", []),
                clinicalInput=data.get("clinicalInput"),
                clinicalInputVersion=data.get("clinicalInputVersion", "1.0"),
                aiOutput=data.get("aiOutput"),
                createdAt=iso,
            )
            session.add(obj)
            session.commit()
            session.refresh(obj)
            return _model_to_dict(obj)
        finally:
            session.close()

    def list_ai_audit_trail(self, case_id: Optional[str] = None, tenant_id: Optional[str] = None) -> list[dict[str, Any]]:
        session = SessionLocal()
        try:
            query = session.query(AiAuditTrailModel)
            if case_id:
                query = query.filter(AiAuditTrailModel.caseId == case_id)
            if tenant_id:
                case_ids = [c.id for c in session.query(DermCaseModel.id).filter(DermCaseModel.tenantId == tenant_id).all()]
                query = query.filter(AiAuditTrailModel.caseId.in_(case_ids))
            query = query.order_by(AiAuditTrailModel.createdAt.desc())
            return [_model_to_dict(i) for i in query.all()]
        finally:
            session.close()

    def add_specialist_review(self, data: dict[str, Any], specialist_id: str) -> dict[str, Any]:
        session = SessionLocal()
        try:
            iso = _now_iso()
            obj = SpecialistReviewModel(
                id=_uid("sr"),
                caseId=data["caseId"],
                specialistId=specialist_id,
                finalDecisionTimestamp=iso,
                finalAssessment=data.get("finalAssessment"),
                finalCondition=data.get("finalCondition"),
                clinicalAction=data.get("clinicalAction"),
                treatmentGuidance=data.get("treatmentGuidance"),
                followUpPeriodWeeks=data.get("followUpPeriodWeeks"),
                specialistNotes=data.get("specialistNotes"),
                confirmsAiAssessment=data.get("confirmsAiAssessment"),
                partialEndorsement=data.get("partialEndorsement"),
                data=data,
            )
            session.add(obj)
            session.commit()
            session.refresh(obj)
            return _model_to_dict(obj)
        finally:
            session.close()

    def list_specialist_reviews(self, case_id: Optional[str] = None) -> list[dict[str, Any]]:
        session = SessionLocal()
        try:
            query = session.query(SpecialistReviewModel)
            if case_id:
                query = query.filter(SpecialistReviewModel.caseId == case_id)
            query = query.order_by(SpecialistReviewModel.finalDecisionTimestamp.desc())
            return [_model_to_dict(i) for i in query.all()]
        finally:
            session.close()


store = DatabaseStore()
