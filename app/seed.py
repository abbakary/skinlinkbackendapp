"""Seed file for initial database setup. Seeds only the provider (platform admin) account."""

from datetime import datetime, timezone

DEMO_PLATFORM_PASSWORD = "platform123"
DEMO_ORG_PASSWORD = "clinic123"


def hours_ago(h: float) -> str:
    from datetime import timedelta
    return (datetime.now(timezone.utc) - timedelta(hours=h)).isoformat()


def seed_db():
    from app.config import settings
    from app.database import SessionLocal, UserModel, init_db

    init_db()
    db = SessionLocal()
    try:
        admin_email = settings.platform_admin_email.lower()
        existing = db.query(UserModel).filter(UserModel.email == admin_email).first()
        if not existing:
            admin_user = UserModel(
                id="u_platform",
                tenantId=None,
                name="SkinLink Operator",
                email=admin_email,
                role="platform_admin",
                title="Platform Administrator",
                status="active",
                avatarColor="#0c2340",
                lastActive=datetime.now(timezone.utc).isoformat(),
                createdAt=datetime.now(timezone.utc).isoformat(),
            )
            db.add(admin_user)
            db.commit()
    finally:
        db.close()
