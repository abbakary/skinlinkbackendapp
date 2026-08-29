import os
from pathlib import Path
from sqlalchemy import create_engine, Column, String, Integer, Boolean, Float, Text, JSON, ForeignKey, DateTime
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
from app.config import settings

db_url = settings.database_url
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)

connect_args = {}
if db_url.startswith("sqlite"):
    connect_args["check_same_thread"] = False
    # Ensure data folder exists for SQLite
    if "sqlite:///" in db_url:
        sqlite_path = db_url.replace("sqlite:///", "")
        db_dir = os.path.dirname(sqlite_path)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)

engine = create_engine(db_url, connect_args=connect_args, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class TenantModel(Base):
    __tablename__ = "tenants"

    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    slug = Column(String, nullable=False, index=True)
    plan = Column(String, default="pilot")
    status = Column(String, default="active")
    country = Column(String, nullable=False)
    region = Column(String, nullable=False)
    district = Column(String, nullable=True)
    facilityRegNumber = Column(String, nullable=True)
    facilityType = Column(String, nullable=True)
    contactName = Column(String, nullable=False)
    contactEmail = Column(String, nullable=False)
    contactPhone = Column(String, nullable=True)
    dpo = Column(JSON, nullable=True)
    seats = Column(Integer, default=10)
    usedSeats = Column(Integer, default=0)
    clinics = Column(Integer, default=1)
    createdAt = Column(String, nullable=False)
    primaryColor = Column(String, default="#1f7a8c")
    messages = Column(JSON, default=list)


class UserModel(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True)
    tenantId = Column(String, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True, index=True)
    name = Column(String, nullable=False)
    email = Column(String, nullable=False, unique=True, index=True)
    passwordHash = Column(String, nullable=True) # or stored credential
    role = Column(String, nullable=False)
    title = Column(String, nullable=True)
    specialty = Column(String, nullable=True)
    phone = Column(String, nullable=True)
    status = Column(String, default="active")
    avatarColor = Column(String, default="#0c2340")
    lastActive = Column(String, nullable=False)
    createdAt = Column(String, nullable=False)
    
    # Regulatory & Verification fields
    verificationLevel = Column(Integer, default=0)
    nidaNumber = Column(String, nullable=True)
    passportPhotoUrl = Column(String, nullable=True)
    mctRegistrationNumber = Column(String, nullable=True)
    tnmcRegistrationNumber = Column(String, nullable=True)
    licenceNumber = Column(String, nullable=True)
    licenceExpiry = Column(String, nullable=True)
    licenceStatus = Column(String, nullable=True)
    specialistQualification = Column(String, nullable=True)
    practiceName = Column(String, nullable=True)
    facilityRegNumber = Column(String, nullable=True)
    indemnityInsurer = Column(String, nullable=True)
    indemnityPolicyNumber = Column(String, nullable=True)
    indemnityExpiry = Column(String, nullable=True)
    documents = Column(JSON, nullable=True)


class PatientModel(Base):
    __tablename__ = "patients"

    id = Column(String, primary_key=True)
    tenantId = Column(String, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    code = Column(String, nullable=False, index=True)
    fullName = Column(String, nullable=False)
    age = Column(Integer, nullable=False)
    gender = Column(String, nullable=False)
    phone = Column(String, nullable=True)
    alternatePhone = Column(String, nullable=True)
    village = Column(String, nullable=False)
    region = Column(String, nullable=True)
    district = Column(String, nullable=True)
    country = Column(String, nullable=True)
    medicalHistory = Column(Text, nullable=True)
    allergies = Column(Text, nullable=True)
    currentMedications = Column(Text, nullable=True)
    chronicConditions = Column(Text, nullable=True)
    preferredLanguage = Column(String, nullable=True)
    consentObtained = Column(Boolean, default=False)
    consentDate = Column(String, nullable=True)
    consentWitness = Column(String, nullable=True)
    consentForPhotography = Column(Boolean, default=False)
    consentForRemoteReview = Column(Boolean, default=False)
    consentForStorage = Column(Boolean, default=False)
    registeredById = Column(String, nullable=False)
    createdAt = Column(String, nullable=False)
    notes = Column(Text, nullable=True)


class DermCaseModel(Base):
    __tablename__ = "cases"

    id = Column(String, primary_key=True)
    tenantId = Column(String, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    ref = Column(String, nullable=False, index=True)
    patientId = Column(String, ForeignKey("patients.id", ondelete="CASCADE"), nullable=False, index=True)
    clinicianId = Column(String, nullable=False)
    specialistId = Column(String, nullable=True)
    primaryConcern = Column(Text, nullable=False)
    clinicalInfo = Column(Text, nullable=False)
    durationDays = Column(Integer, default=0)
    suspectedCondition = Column(String, nullable=True)
    bodySite = Column(String, nullable=True)
    previousTreatment = Column(Text, nullable=True)
    redFlags = Column(JSON, default=list)
    symptoms = Column(JSON, default=list)
    severity = Column(String, nullable=True)
    status = Column(String, default="new", index=True)
    priority = Column(String, default="routine")
    images = Column(JSON, default=list)
    ai = Column(JSON, nullable=True)
    aiImageQuality = Column(JSON, nullable=True)
    imageQualityStatus = Column(String, nullable=True)
    treatmentPlan = Column(JSON, nullable=True)
    followUpReport = Column(JSON, nullable=True)
    notes = Column(JSON, default=list)
    createdAt = Column(String, nullable=False)
    updatedAt = Column(String, nullable=False)


class ReferralModel(Base):
    __tablename__ = "referrals"

    id = Column(String, primary_key=True)
    tenantId = Column(String, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    ref = Column(String, nullable=False)
    caseId = Column(String, nullable=False, index=True)
    patientName = Column(String, nullable=False)
    fromClinic = Column(String, nullable=False)
    toSpecialistId = Column(String, nullable=True)
    status = Column(String, default="pending")
    priority = Column(String, default="routine")
    createdAt = Column(String, nullable=False)
    respondedAt = Column(String, nullable=True)


class FollowUpModel(Base):
    __tablename__ = "follow_ups"

    id = Column(String, primary_key=True)
    tenantId = Column(String, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    caseId = Column(String, nullable=False, index=True)
    caseRef = Column(String, nullable=False)
    patientName = Column(String, nullable=False)
    scheduledFor = Column(String, nullable=False)
    status = Column(String, default="scheduled")
    assignedToId = Column(String, nullable=True)
    purpose = Column(Text, nullable=False)
    outcome = Column(Text, nullable=True)
    followUpReport = Column(JSON, nullable=True)


class ResourceModel(Base):
    __tablename__ = "resources"

    id = Column(String, primary_key=True)
    tenantId = Column(String, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    title = Column(String, nullable=False)
    category = Column(String, nullable=False)
    type = Column(String, nullable=False)
    description = Column(Text, nullable=False)
    updatedAt = Column(String, nullable=False)


class DraftModel(Base):
    __tablename__ = "drafts"

    id = Column(String, primary_key=True)
    userId = Column(String, nullable=False, index=True)
    data = Column(JSON, nullable=False)
    updatedAt = Column(String, nullable=False)


class ApplicationModel(Base):
    __tablename__ = "applications"

    id = Column(String, primary_key=True)
    applicationType = Column(String, nullable=False)
    status = Column(String, default="pending", index=True)
    verificationLevel = Column(Integer, default=0)
    submittedAt = Column(String, nullable=False)
    reviewedAt = Column(String, nullable=True)
    reviewedBy = Column(String, nullable=True)
    reviewNotes = Column(Text, nullable=True)
    verifiedItems = Column(JSON, default=list)
    data = Column(JSON, nullable=False)


class ApiKeyApplicationModel(Base):
    __tablename__ = "api_key_applications"

    id = Column(String, primary_key=True)
    status = Column(String, default="pending", index=True)
    submittedAt = Column(String, nullable=False)
    data = Column(JSON, nullable=False)


class ApiKeyModel(Base):
    __tablename__ = "api_keys"

    id = Column(String, primary_key=True)
    keyHash = Column(String, nullable=False, index=True)
    createdAt = Column(String, nullable=False)
    data = Column(JSON, nullable=False)


class AiAuditTrailModel(Base):
    __tablename__ = "ai_audit_trail"

    id = Column(String, primary_key=True)
    caseId = Column(String, nullable=True, index=True)
    requestType = Column(String, nullable=False)
    aiModel = Column(String, nullable=False)
    requestTimestamp = Column(String, nullable=False)
    imageIds = Column(JSON, default=list)
    clinicalInput = Column(JSON, nullable=True)
    clinicalInputVersion = Column(String, nullable=True)
    aiOutput = Column(JSON, nullable=True)
    createdAt = Column(String, nullable=False)


class SpecialistReviewModel(Base):
    __tablename__ = "specialist_reviews"

    id = Column(String, primary_key=True)
    caseId = Column(String, nullable=False, index=True)
    specialistId = Column(String, nullable=False, index=True)
    finalDecisionTimestamp = Column(String, nullable=False)
    finalAssessment = Column(Text, nullable=True)
    finalCondition = Column(String, nullable=True)
    clinicalAction = Column(String, nullable=True)
    treatmentGuidance = Column(Text, nullable=True)
    followUpPeriodWeeks = Column(Integer, nullable=True)
    specialistNotes = Column(Text, nullable=True)
    confirmsAiAssessment = Column(Boolean, nullable=True)
    partialEndorsement = Column(Boolean, nullable=True)
    data = Column(JSON, nullable=False)


def init_db():
    Base.metadata.create_all(bind=engine)
