from typing import Any, Literal, Optional
from pydantic import BaseModel, EmailStr, Field


UserRole = Literal["platform_admin", "org_admin", "specialist", "clinician"]
TenantStatus = Literal["active", "trial", "suspended", "pending"]
TenantPlan = Literal["pilot", "growth", "enterprise"]

# ── Application / registration types ─────────────────────────────────────────
ApplicationType = Literal["organization", "solo_dermatologist", "nurse", "facility_doctor"]
ApplicationStatus = Literal["pending", "approved", "rejected"]
VerificationLevel = Literal[0, 1, 2, 3, 4, 5]
# 0=Registered, 1=Identity Verified, 2=Professional Verified,
# 3=Specialist Verified, 4=Practice Verified, 5=Clinical Provider Approved
Gender = Literal["Male", "Female", "Other"]
CaseStatus = Literal["new", "in_review", "reviewed", "follow_up", "closed"]
CasePriority = Literal["routine", "urgent", "emergency"]
ReferralStatus = Literal["pending", "accepted", "responded", "declined"]
FollowUpStatus = Literal["scheduled", "due", "overdue", "completed"]
ImageQuality = Literal["good", "acceptable", "poor"]
ResourceType = Literal["PDF", "Video", "Article", "Protocol"]
UserStatus = Literal["active", "invited", "disabled"]

ImageQualityRating = Literal["good", "acceptable", "poor"]
UrgencyLevel = Literal["routine", "urgent", "emergency"]
Likelihood = Literal["unlikely", "possible", "probable", "highly_likely"]
Confidence = Literal["low", "moderate", "high"]
SpecialistAction = Literal["discharge", "continue_regimen", "adjust_regimen", "escalate_in_person"]


class LoginRequest(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: dict[str, Any]
    tenant: Optional[dict[str, Any]] = None


class PatientCreate(BaseModel):
    # ── Required demographics ──────────────────────────────────────────────
    fullName: str
    age: int
    gender: Gender
    village: str
    # ── Location ───────────────────────────────────────────────────────────
    region: Optional[str] = None
    district: Optional[str] = None
    country: Optional[str] = None
    # ── Contact ────────────────────────────────────────────────────────────
    phone: Optional[str] = None
    alternatePhone: Optional[str] = None
    # ── Clinical history (required for quality referral) ───────────────────
    medicalHistory: Optional[str] = None
    allergies: Optional[str] = None
    currentMedications: Optional[str] = None
    chronicConditions: Optional[str] = None
    # ── Preferred language ─────────────────────────────────────────────────
    preferredLanguage: Optional[str] = None
    # ── Consent (structured — not just a boolean) ──────────────────────────
    consentObtained: bool = False
    consentDate: Optional[str] = None          # ISO date string
    consentWitness: Optional[str] = None       # name of witness / staff member
    consentForPhotography: bool = False
    consentForRemoteReview: bool = False
    consentForStorage: bool = False
    # ── Free-form notes ────────────────────────────────────────────────────
    notes: Optional[str] = None


class PatientUpdate(BaseModel):
    fullName: Optional[str] = None
    age: Optional[int] = None
    gender: Optional[Gender] = None
    village: Optional[str] = None
    district: Optional[str] = None
    country: Optional[str] = None
    phone: Optional[str] = None
    alternatePhone: Optional[str] = None
    medicalHistory: Optional[str] = None
    allergies: Optional[str] = None
    currentMedications: Optional[str] = None
    chronicConditions: Optional[str] = None
    preferredLanguage: Optional[str] = None
    consentObtained: Optional[bool] = None
    consentDate: Optional[str] = None
    consentWitness: Optional[str] = None
    consentForPhotography: Optional[bool] = None
    consentForRemoteReview: Optional[bool] = None
    consentForStorage: Optional[bool] = None
    notes: Optional[str] = None


class LesionImageIn(BaseModel):
    url: str
    angle: str
    quality: ImageQuality = "good"
    qualityScore: int = 85
    qualityNotes: Optional[str] = None


class CaseCreate(BaseModel):
    patientId: str
    primaryConcern: str
    clinicalInfo: str = ""
    durationDays: int
    suspectedCondition: str = "Awaiting specialist review"
    priority: CasePriority = "routine"
    images: list[LesionImageIn] = Field(default_factory=list)
    bodySite: Optional[str] = None
    previousTreatment: Optional[str] = None
    redFlags: Optional[list[str]] = None
    symptoms: Optional[list[str]] = None
    severity: Optional[Literal["mild", "moderate", "severe"]] = None


class CaseUpdate(BaseModel):
    status: Optional[CaseStatus] = None
    priority: Optional[CasePriority] = None
    specialistId: Optional[str] = None
    suspectedCondition: Optional[str] = None
    clinicalInfo: Optional[str] = None
    treatmentPlan: Optional[dict[str, Any]] = None
    followUpReport: Optional[dict[str, Any]] = None
    ai: Optional[dict[str, Any]] = None


class CaseNoteCreate(BaseModel):
    body: str


class ReferralCreate(BaseModel):
    caseId: str
    patientName: str
    fromClinic: str
    priority: CasePriority = "routine"


class ReferralUpdate(BaseModel):
    status: Optional[ReferralStatus] = None
    toSpecialistId: Optional[str] = None
    respondedAt: Optional[str] = None


class TenantCreate(BaseModel):
    name: str
    region: str
    country: str
    plan: TenantPlan = "pilot"
    seats: int = 10
    clinics: int = 1
    primaryColor: Optional[str] = None
    adminName: str
    adminEmail: EmailStr
    adminPassword: str
    adminTitle: Optional[str] = None
    adminPhone: Optional[str] = None


class TenantUpdate(BaseModel):
    name: Optional[str] = None
    status: Optional[TenantStatus] = None
    plan: Optional[TenantPlan] = None
    seats: Optional[int] = None
    clinics: Optional[int] = None
    primaryColor: Optional[str] = None
    contactName: Optional[str] = None
    contactEmail: Optional[str] = None


class UserCreate(BaseModel):
    tenantId: str
    name: str
    email: EmailStr
    role: UserRole
    password: str
    title: Optional[str] = None
    specialty: Optional[str] = None
    phone: Optional[str] = None


class UserUpdate(BaseModel):
    name: Optional[str] = None
    role: Optional[UserRole] = None
    title: Optional[str] = None
    specialty: Optional[str] = None
    phone: Optional[str] = None
    status: Optional[UserStatus] = None


class UserPasswordReset(BaseModel):
    password: str


class ResourceCreate(BaseModel):
    title: str
    category: str
    type: ResourceType
    description: str


class FollowUpCreate(BaseModel):
    caseId: str
    caseRef: str
    patientName: str
    scheduledFor: str
    purpose: str
    status: FollowUpStatus = "scheduled"


class FollowUpUpdate(BaseModel):
    status: Optional[FollowUpStatus] = None
    outcome: Optional[str] = None
    purpose: Optional[str] = None
    followUpReport: Optional[dict[str, Any]] = None


class DraftReferral(BaseModel):
    id: str
    step: int = 0
    patient: Optional[dict[str, Any]] = None
    images: list[dict[str, Any]] = Field(default_factory=list)
    clinical: Optional[dict[str, Any]] = None
    updatedAt: str


class SyncStatus(BaseModel):
    online: bool
    pendingDrafts: int
    lastSyncedAt: Optional[str] = None


class AiImageQualityCheck(BaseModel):
    rating: ImageQualityRating
    focus: bool
    lighting: bool
    lesion_visible: bool
    required_angles_present: bool = True
    issues: list[str] = Field(default_factory=list)
    score: int = Field(ge=0, le=100, default=85)


class AiPossibleCondition(BaseModel):
    condition: str
    likelihood: Likelihood
    probability: Optional[int] = Field(None, ge=0, le=100)
    rationale: Optional[str] = None


class AiAssessmentOutput(BaseModel):
    image_quality: AiImageQualityCheck
    observations: list[str] = Field(default_factory=list)
    possible_conditions: list[AiPossibleCondition] = Field(default_factory=list)
    urgency: UrgencyLevel
    missing_information: list[str] = Field(default_factory=list)
    red_flags_detected: bool = False
    detected_red_flags: list[str] = Field(default_factory=list)
    suggested_next_step: str = "specialist_review"
    confidence: Confidence = "moderate"
    disclaimer: str = "AI assistance only; specialist confirmation required."
    model: str = ""
    generated_at: str = ""


class SkinAssessmentRequest(BaseModel):
    case_id: Optional[str] = None
    patient_age: Optional[int] = None
    sex: Optional[Literal["male", "female", "other"]] = None
    symptoms: list[str] = Field(default_factory=list)
    duration: Optional[str] = None
    duration_days: Optional[int] = None
    body_site: Optional[str] = None
    severity: Optional[Literal["mild", "moderate", "severe"]] = None
    previous_treatment: Optional[str] = None
    treatment_response: Optional[str] = None
    adherence: Optional[Literal["full", "partial", "none"]] = None
    red_flags: list[str] = Field(default_factory=list)
    primary_concern: Optional[str] = None
    clinical_info: Optional[str] = None
    images: list[LesionImageIn] = Field(default_factory=list)
    image_urls: list[str] = Field(default_factory=list)


class ImageQualityCheckRequest(BaseModel):
    image_url: str
    angle: Optional[str] = None
    required_angles: list[str] = Field(default_factory=list)


class ImageQualityCheckResponse(BaseModel):
    image_quality: AiImageQualityCheck
    model: str = ""
    generated_at: str = ""
    retake_required: bool = False


class AiAuditTrailEntry(BaseModel):
    id: Optional[str] = None
    case_id: str
    ai_model: str
    request_timestamp: str
    image_ids: list[str] = Field(default_factory=list)
    clinical_input: dict[str, Any] = Field(default_factory=dict)
    clinical_input_version: str = "1.0"
    ai_output: dict[str, Any] = Field(default_factory=dict)
    request_type: Literal["image_quality_check", "skin_assessment"] = "skin_assessment"


class SpecialistReviewRequest(BaseModel):
    case_id: str
    final_assessment: str
    final_condition: Optional[str] = None
    clinical_action: SpecialistAction
    treatment_guidance: Optional[str] = None
    follow_up_period_weeks: Optional[int] = None
    specialist_notes: Optional[str] = None
    treatment_plan: Optional[dict[str, Any]] = None
    confirms_ai_assessment: Optional[bool] = None
    partial_endorsement: Optional[str] = None


# ── Public registration / application schemas ─────────────────────────────────

class DocumentAttachmentSchema(BaseModel):
    id: Optional[str] = None
    type: str
    label: str
    url: str
    uploadedAt: Optional[str] = None
    verified: bool = False


class DpoDetailsSchema(BaseModel):
    name: str
    title: Optional[str] = None
    email: EmailStr
    phone: str
    pdpcRegistrationNumber: Optional[str] = None
    appointmentLetterUrl: Optional[str] = None


class OrgApplicationCreate(BaseModel):
    """Submitted by an organisation (hospital/clinic) requesting a SkinLink account."""
    applicationType: ApplicationType = "organization"
    # Organisation details
    orgName: str
    orgType: str                   # e.g. "Hospital", "Clinic", "Health Centre"
    orgRegNumber: Optional[str] = None
    region: str
    district: Optional[str] = None
    country: str = "Tanzania"
    address: Optional[str] = None
    facilityRegNumber: Optional[str] = None  # MoH HFR registration
    facilityType: Optional[str] = None
    # Contact / admin
    contactName: str
    contactTitle: Optional[str] = None
    contactEmail: EmailStr
    contactPhone: str
    # Data Protection Officer (PDPC Tanzania requirement)
    dpo: Optional[DpoDetailsSchema] = None
    # Documents & Plan & Selected Package
    documents: Optional[list[DocumentAttachmentSchema]] = None
    plan: TenantPlan = "pilot"
    seats: int = 10
    selectedPackage: Optional[dict[str, Any]] = None
    requestedPassword: Optional[str] = None
    agreeTerms: bool = False
    agreeDataPolicy: bool = False


class NurseApplicationCreate(BaseModel):
    """Submitted by a frontline nurse or village health worker."""
    applicationType: ApplicationType = "nurse"
    fullName: str
    dateOfBirth: Optional[str] = None
    nidaNumber: Optional[str] = None
    nationality: str = "Tanzanian"
    email: EmailStr
    phone: str
    region: str
    district: Optional[str] = None
    village: Optional[str] = None
    nursingQualification: Optional[str] = None # e.g. "Diploma in Nursing", "Enrolled Nurse"
    tnmcRegistrationNumber: str                # Tanzania Nursing & Midwifery Council
    licenceNumber: str
    licenceExpiry: Optional[str] = None
    facilityName: str
    facilityRegNumber: Optional[str] = None    # MoH HFR
    passportPhotoUrl: Optional[str] = None
    documents: Optional[list[DocumentAttachmentSchema]] = None
    requestedPassword: Optional[str] = None
    agreeTerms: bool = False
    agreeDataPolicy: bool = False


class FacilityDoctorApplicationCreate(BaseModel):
    """Submitted by a registered doctor or dermatologist affiliated with a health facility."""
    applicationType: ApplicationType = "facility_doctor"
    fullName: str
    dateOfBirth: Optional[str] = None
    nidaNumber: Optional[str] = None
    nationality: str = "Tanzanian"
    email: EmailStr
    phone: str
    region: str
    district: Optional[str] = None
    professionalTitle: Optional[str] = None   # e.g. "MD", "MMed Dermatology"
    specialty: str = "General Dermatology"
    mctRegistrationNumber: str                # Medical Council of Tanganyika
    licenceNumber: str
    licenceExpiry: Optional[str] = None
    specialistQualification: Optional[str] = None
    facilityName: str
    facilityRegNumber: Optional[str] = None    # MoH HFR
    passportPhotoUrl: Optional[str] = None
    documents: Optional[list[DocumentAttachmentSchema]] = None
    requestedPassword: Optional[str] = None
    agreeTerms: bool = False
    agreeDataPolicy: bool = False
    agreeTelemedicineTerms: bool = False


class SoloDermatologistApplicationCreate(BaseModel):
    """Submitted by an independent/solo dermatologist requesting a verified account."""
    applicationType: ApplicationType = "solo_dermatologist"
    # Identity
    fullName: str
    dateOfBirth: Optional[str] = None
    nidaNumber: Optional[str] = None
    nationality: str = "Tanzanian"
    passportPhotoUrl: Optional[str] = None
    email: EmailStr
    phone: str
    practiceAddress: str
    region: str
    district: Optional[str] = None
    country: str = "Tanzania"
    # Professional
    professionalTitle: Optional[str] = None   # e.g. "MD", "MMED Dermatology"
    specialty: str = "Dermatology"
    mctRegistrationNumber: str
    licenceNumber: str
    licenceExpiry: Optional[str] = None
    specialistQualification: Optional[str] = None  # e.g. "MMed Dermatology"
    # Practice & Indemnity Insurance
    practiceName: Optional[str] = None
    practiceRegNumber: Optional[str] = None
    tinNumber: Optional[str] = None
    indemnityInsurer: Optional[str] = None
    indemnityPolicyNumber: Optional[str] = None
    indemnityExpiry: Optional[str] = None
    indemnityCoverage: Optional[str] = None
    # Documents & Selected Package
    documents: Optional[list[DocumentAttachmentSchema]] = None
    selectedPackage: Optional[dict[str, Any]] = None
    requestedPassword: Optional[str] = None
    agreeTerms: bool = False
    agreeDataPolicy: bool = False
    agreeTelemedicineTerms: bool = False


class ApplicationReview(BaseModel):
    """Platform admin action to approve or reject an application."""
    status: ApplicationStatus
    reviewNotes: Optional[str] = None
    verificationLevel: Optional[VerificationLevel] = None
    verifiedItems: Optional[list[str]] = None


class PackageSchema(BaseModel):
    """Canonical SkinLink package definition — mirrors lib/packages.ts."""
    name: str
    amount: int                          # TZS integer
    billingCycle: Literal["monthly", "quarterly", "annually"] = "monthly"
    badge: str
    desc: str
    seats: str
    forTypes: list[Literal["org", "solo", "nurse"]]
    features: list[str] = []
    highlight: bool = False


class SelectedPackage(BaseModel):
    """Package selected by a client — stored on application & tenant."""
    packageName: str
    amount: int
    currency: str = "TZS"
    billingCycle: Literal["monthly", "quarterly", "annually"] = "monthly"
