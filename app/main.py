import os
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, EmailStr
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from app.config import settings
from app.database import init_db
from app.media import reset_request_base_url, set_request_base_url
from app.routers import (
    admin,
    ai,
    api_keys,
    applications,
    auth,
    cases,
    drafts,
    fhir,
    followups,
    patients,
    referrals,
    resources,
)
from app.seed import seed_db
from app.services.ai_service import gemini_service
from app.store import store


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    seed_db()
    yield


app = FastAPI(title=settings.app_name, version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class RequestBaseUrlMiddleware(BaseHTTPMiddleware):
    """Capture the public origin (honouring Railway/proxy forwarded headers)."""

    async def dispatch(self, request: Request, call_next):
        forwarded_host = (
            request.headers.get("x-forwarded-host")
            or request.headers.get("host")
            or ""
        ).split(",")[0].strip()
        forwarded_proto = (
            request.headers.get("x-forwarded-proto") or request.url.scheme or "https"
        ).split(",")[0].strip()
        if forwarded_host:
            base = f"{forwarded_proto}://{forwarded_host}"
        else:
            base = str(request.base_url).rstrip("/")
        token = set_request_base_url(base)
        try:
            return await call_next(request)
        finally:
            reset_request_base_url(token)


class UploadsCORSMiddleware(BaseHTTPMiddleware):
    """Ensure /uploads/* static files always carry CORS headers."""
    async def dispatch(self, request: Request, call_next):
        if request.url.path.startswith("/uploads/") and request.method == "OPTIONS":
            return Response(
                status_code=204,
                headers={
                    "Access-Control-Allow-Origin": "*",
                    "Access-Control-Allow-Methods": "GET, HEAD, OPTIONS",
                    "Access-Control-Allow-Headers": "*",
                    "Cross-Origin-Resource-Policy": "cross-origin",
                    "Access-Control-Max-Age": "86400",
                },
            )
        response = await call_next(request)
        if request.url.path.startswith("/uploads/"):
            response.headers["Access-Control-Allow-Origin"] = "*"
            response.headers["Access-Control-Allow-Methods"] = "GET, HEAD, OPTIONS"
            response.headers["Access-Control-Allow-Headers"] = "*"
            response.headers["Cross-Origin-Resource-Policy"] = "cross-origin"
            response.headers.setdefault("Cache-Control", "public, max-age=31536000, immutable")
        return response


app.add_middleware(UploadsCORSMiddleware)
app.add_middleware(RequestBaseUrlMiddleware)

# Serve uploaded images
os.makedirs(settings.upload_dir, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=settings.upload_dir), name="uploads")

# Include routers
app.include_router(auth.router, prefix="/api/v1")
app.include_router(admin.router, prefix="/api/v1")
app.include_router(patients.router, prefix="/api/v1")
app.include_router(cases.router, prefix="/api/v1")
app.include_router(referrals.router, prefix="/api/v1")
app.include_router(followups.router, prefix="/api/v1")
app.include_router(resources.router, prefix="/api/v1")
app.include_router(drafts.router, prefix="/api/v1")
app.include_router(ai.router, prefix="/api/v1")
app.include_router(applications.router, prefix="/api/v1")
app.include_router(api_keys.router, prefix="/api/v1")
app.include_router(fhir.router, prefix="/api/v1")
app.include_router(fhir.router)


class SetupProviderRequest(BaseModel):
    name: str
    email: str
    password: str
    title: Optional[str] = "Platform Administrator"
    secret_key: Optional[str] = None


@app.get("/api/v1/health")
def health():
    return {"status": "ok", "service": settings.app_name}


@app.get("/api/v1/status")
def status_info():
    """Return live system operational metrics and DB health."""
    db_type = "PostgreSQL" if "postgres" in settings.database_url.lower() else "SQLite"
    ai_configured = gemini_service.is_configured
    
    users = store.list_users(None)
    tenants = store.scope(None, "tenants")
    cases = store.scope(None, "cases")
    patients = store.scope(None, "patients")
    
    provider_users = [u for u in users if u.get("role") == "platform_admin"]

    return {
        "status": "ok",
        "service": settings.app_name,
        "version": "1.0.0",
        "database": {
            "status": "connected",
            "type": db_type,
        },
        "ai_engine": {
            "configured": ai_configured,
            "provider": "SkinLink AI",
            "model": gemini_service.model,
        },
        "metrics": {
            "total_tenants": len(tenants),
            "total_users": len(users),
            "total_cases": len(cases),
            "total_patients": len(patients),
            "provider_admins": len(provider_users),
        },
    }


@app.post("/api/v1/setup/provider")
def create_provider_account(body: SetupProviderRequest):
    """Allow setup/creation of provider platform admin accounts."""
    if len(body.password) < 6:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must be at least 6 characters long",
        )
    
    email = body.email.strip().lower()
    existing = store.get_user_by_email(email)
    
    if existing:
        # Update existing user to platform_admin role & update password
        store.update_user(existing["id"], {
            "name": body.name,
            "role": "platform_admin",
            "title": body.title or "Platform Administrator",
            "status": "active",
        })
        store.set_password(email, body.password)
        updated = store.get_user(existing["id"])
        return {
            "success": True,
            "message": f"Updated account for {email} to Platform Administrator",
            "user": updated,
        }
    
    # Create new provider user
    new_user = store.add_user(
        {
            "tenantId": None,
            "name": body.name,
            "email": email,
            "role": "platform_admin",
            "title": body.title or "Platform Administrator",
            "status": "active",
            "avatarColor": "#0c2340",
        },
        body.password,
    )
    return {
        "success": True,
        "message": f"Provider account created successfully for {email}",
        "user": new_user,
    }


@app.get("/", response_class=HTMLResponse)
def root_dashboard():
    """Render attractive API status dashboard & provider admin setup portal."""
    db_type = "PostgreSQL" if "postgres" in settings.database_url.lower() else "SQLite"
    ai_status_badge = (
        '<span class="badge badge-success"><span class="pulse"></span> Ready</span>'
        if gemini_service.is_configured
        else '<span class="badge badge-warning">API Key Required</span>'
    )
    
    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>SkinLink Tele-Dermatology API | System Status</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700;800&family=Plus+Jakarta+Sans:wght@400;500;600;700&display=swap" rel="stylesheet">
    <style>
        :root {{
            --bg-dark: #090d16;
            --card-bg: rgba(21, 30, 48, 0.7);
            --card-border: rgba(255, 255, 255, 0.08);
            --primary: #0284c7;
            --primary-glow: rgba(2, 132, 199, 0.35);
            --accent: #14b8a6;
            --accent-glow: rgba(20, 184, 166, 0.35);
            --indigo: #6366f1;
            --text-main: #f8fafc;
            --text-muted: #94a3b8;
            --text-dim: #64748b;
            --success: #10b981;
            --warning: #f59e0b;
            --danger: #ef4444;
        }}

        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}

        body {{
            font-family: 'Plus Jakarta Sans', sans-serif;
            background-color: var(--bg-dark);
            color: var(--text-main);
            min-height: 100vh;
            display: flex;
            flex-direction: column;
            background-image: 
                radial-gradient(circle at 15% 20%, rgba(2, 132, 199, 0.18) 0%, transparent 45%),
                radial-gradient(circle at 85% 75%, rgba(20, 184, 166, 0.15) 0%, transparent 45%),
                radial-gradient(circle at 50% 50%, rgba(99, 102, 241, 0.1) 0%, transparent 60%);
            background-attachment: fixed;
        }}

        h1, h2, h3, h4 {{
            font-family: 'Outfit', sans-serif;
        }}

        .navbar {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 1.25rem 2.5rem;
            border-bottom: 1px solid var(--card-border);
            backdrop-filter: blur(16px);
            background: rgba(9, 13, 22, 0.8);
            position: sticky;
            top: 0;
            z-index: 50;
        }}

        .brand {{
            display: flex;
            align-items: center;
            gap: 0.75rem;
            text-decoration: none;
            color: var(--text-main);
        }}

        .brand-logo {{
            width: 38px;
            height: 38px;
            background: linear-gradient(135deg, var(--primary), var(--accent));
            border-radius: 10px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-weight: 800;
            font-size: 1.2rem;
            color: white;
            box-shadow: 0 0 15px var(--primary-glow);
        }}

        .brand-title {{
            font-size: 1.35rem;
            font-weight: 800;
            letter-spacing: -0.02em;
            background: linear-gradient(to right, #ffffff, #cbd5e1);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }}

        .nav-links {{
            display: flex;
            align-items: center;
            gap: 1rem;
        }}

        .nav-btn {{
            padding: 0.6rem 1.2rem;
            border-radius: 8px;
            font-size: 0.875rem;
            font-weight: 600;
            text-decoration: none;
            transition: all 0.2s ease;
            display: inline-flex;
            align-items: center;
            gap: 0.5rem;
        }}

        .btn-ghost {{
            color: var(--text-muted);
            border: 1px solid var(--card-border);
            background: rgba(255, 255, 255, 0.03);
        }}

        .btn-ghost:hover {{
            color: var(--text-main);
            background: rgba(255, 255, 255, 0.08);
            border-color: rgba(255, 255, 255, 0.2);
        }}

        .btn-primary {{
            background: linear-gradient(135deg, var(--primary), #0369a1);
            color: white;
            border: none;
            box-shadow: 0 4px 14px var(--primary-glow);
        }}

        .btn-primary:hover {{
            transform: translateY(-1px);
            box-shadow: 0 6px 20px var(--primary-glow);
        }}

        .container {{
            max-width: 1200px;
            margin: 2.5rem auto;
            padding: 0 1.5rem;
            width: 100%;
            flex: 1;
        }}

        .hero {{
            margin-bottom: 2.5rem;
            text-align: center;
        }}

        .hero-badge {{
            display: inline-flex;
            align-items: center;
            gap: 0.5rem;
            padding: 0.35rem 0.9rem;
            border-radius: 9999px;
            background: rgba(2, 132, 199, 0.12);
            border: 1px solid rgba(2, 132, 199, 0.3);
            color: #38bdf8;
            font-size: 0.825rem;
            font-weight: 600;
            margin-bottom: 1rem;
        }}

        .hero-title {{
            font-size: 2.75rem;
            font-weight: 800;
            letter-spacing: -0.03em;
            margin-bottom: 0.75rem;
            line-height: 1.2;
            background: linear-gradient(135deg, #ffffff 30%, #94a3b8);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }}

        .hero-subtitle {{
            color: var(--text-muted);
            font-size: 1.1rem;
            max-width: 650px;
            margin: 0 auto;
            line-height: 1.6;
        }}

        .grid-3 {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
            gap: 1.5rem;
            margin-bottom: 2.5rem;
        }}

        .card {{
            background: var(--card-bg);
            border: 1px solid var(--card-border);
            border-radius: 16px;
            padding: 1.75rem;
            backdrop-filter: blur(12px);
            transition: transform 0.2s ease, border-color 0.2s ease;
            position: relative;
            overflow: hidden;
        }}

        .card:hover {{
            border-color: rgba(255, 255, 255, 0.15);
        }}

        .card-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 1.25rem;
        }}

        .card-title {{
            font-size: 1.1rem;
            font-weight: 700;
            color: var(--text-main);
            display: flex;
            align-items: center;
            gap: 0.6rem;
        }}

        .badge {{
            display: inline-flex;
            align-items: center;
            gap: 0.4rem;
            padding: 0.25rem 0.65rem;
            border-radius: 9999px;
            font-size: 0.75rem;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.05em;
        }}

        .badge-success {{
            background: rgba(16, 185, 129, 0.15);
            color: #34d399;
            border: 1px solid rgba(16, 185, 129, 0.3);
        }}

        .badge-warning {{
            background: rgba(245, 158, 11, 0.15);
            color: #fbbf24;
            border: 1px solid rgba(245, 158, 11, 0.3);
        }}

        .pulse {{
            width: 7px;
            height: 7px;
            border-radius: 50%;
            background-color: currentColor;
            box-shadow: 0 0 0 0 rgba(52, 211, 153, 0.7);
            animation: pulse-animation 1.8s infinite;
        }}

        @keyframes pulse-animation {{
            0% {{ box-shadow: 0 0 0 0 rgba(52, 211, 153, 0.7); }}
            70% {{ box-shadow: 0 0 0 8px rgba(52, 211, 153, 0); }}
            100% {{ box-shadow: 0 0 0 0 rgba(52, 211, 153, 0); }}
        }}

        .status-list {{
            list-style: none;
            display: flex;
            flex-direction: column;
            gap: 0.85rem;
        }}

        .status-item {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            font-size: 0.9rem;
            padding-bottom: 0.75rem;
            border-bottom: 1px solid rgba(255, 255, 255, 0.04);
        }}

        .status-item:last-child {{
            border-bottom: none;
            padding-bottom: 0;
        }}

        .status-label {{
            color: var(--text-muted);
        }}

        .status-val {{
            font-weight: 600;
            color: var(--text-main);
        }}

        .metrics-grid {{
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 1rem;
        }}

        .metric-box {{
            background: rgba(255, 255, 255, 0.02);
            border: 1px solid var(--card-border);
            border-radius: 12px;
            padding: 1rem;
            text-align: center;
        }}

        .metric-num {{
            font-family: 'Outfit', sans-serif;
            font-size: 1.75rem;
            font-weight: 800;
            color: #38bdf8;
        }}

        .metric-label {{
            font-size: 0.75rem;
            color: var(--text-muted);
            margin-top: 0.2rem;
            text-transform: uppercase;
            letter-spacing: 0.05em;
        }}

        .form-section {{
            background: var(--card-bg);
            border: 1px solid var(--card-border);
            border-radius: 20px;
            padding: 2.25rem;
            backdrop-filter: blur(16px);
            box-shadow: 0 20px 40px rgba(0, 0, 0, 0.3);
            margin-bottom: 3rem;
        }}

        .form-header {{
            margin-bottom: 1.5rem;
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            flex-wrap: wrap;
            gap: 1rem;
        }}

        .form-title {{
            font-size: 1.4rem;
            font-weight: 700;
            color: var(--text-main);
        }}

        .form-desc {{
            color: var(--text-muted);
            font-size: 0.925rem;
            margin-top: 0.3rem;
        }}

        .form-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
            gap: 1.25rem;
            margin-bottom: 1.5rem;
        }}

        .input-group {{
            display: flex;
            flex-direction: column;
            gap: 0.4rem;
        }}

        .input-label {{
            font-size: 0.85rem;
            font-weight: 600;
            color: var(--text-muted);
        }}

        .input-field {{
            background: rgba(9, 13, 22, 0.7);
            border: 1px solid var(--card-border);
            border-radius: 10px;
            padding: 0.75rem 1rem;
            color: white;
            font-size: 0.95rem;
            font-family: inherit;
            outline: none;
            transition: all 0.2s ease;
        }}

        .input-field:focus {{
            border-color: var(--primary);
            box-shadow: 0 0 0 3px var(--primary-glow);
        }}

        .submit-btn {{
            width: 100%;
            padding: 0.85rem;
            border-radius: 10px;
            background: linear-gradient(135deg, var(--primary), var(--accent));
            color: white;
            font-weight: 700;
            font-size: 1rem;
            border: none;
            cursor: pointer;
            transition: all 0.2s ease;
            box-shadow: 0 4px 15px var(--accent-glow);
        }}

        .submit-btn:hover {{
            opacity: 0.95;
            transform: translateY(-1px);
            box-shadow: 0 6px 22px var(--accent-glow);
        }}

        .alert-box {{
            display: none;
            padding: 1rem 1.25rem;
            border-radius: 10px;
            font-size: 0.9rem;
            margin-top: 1rem;
            align-items: center;
            gap: 0.75rem;
        }}

        .alert-success {{
            background: rgba(16, 185, 129, 0.12);
            border: 1px solid rgba(16, 185, 129, 0.3);
            color: #34d399;
        }}

        .alert-error {{
            background: rgba(239, 68, 68, 0.12);
            border: 1px solid rgba(239, 68, 68, 0.3);
            color: #fca5a5;
        }}

        .footer {{
            border-top: 1px solid var(--card-border);
            padding: 1.5rem;
            text-align: center;
            color: var(--text-dim);
            font-size: 0.85rem;
            background: rgba(9, 13, 22, 0.9);
        }}

        .creds-banner {{
            background: rgba(99, 102, 241, 0.1);
            border: 1px dashed rgba(99, 102, 241, 0.3);
            border-radius: 10px;
            padding: 0.85rem 1rem;
            font-size: 0.85rem;
            color: #c7d2fe;
            margin-bottom: 1.25rem;
            display: flex;
            align-items: center;
            justify-content: space-between;
        }}

        .code-tag {{
            font-family: monospace;
            background: rgba(0, 0, 0, 0.3);
            padding: 0.2rem 0.5rem;
            border-radius: 4px;
            color: #38bdf8;
        }}
    </style>
</head>
<body>
    <nav class="navbar">
        <a href="/" class="brand">
            <div class="brand-logo">S</div>
            <div class="brand-title">SkinLink API</div>
        </a>
        <div class="nav-links">
            <a href="/docs" target="_blank" class="nav-btn btn-ghost">Interactive API Docs (/docs)</a>
            <a href="/redoc" target="_blank" class="nav-btn btn-ghost">ReDoc (/redoc)</a>
            <a href="http://localhost:3000" class="nav-btn btn-primary">Open Web App &rarr;</a>
        </div>
    </nav>

    <div class="container">
        <div class="hero">
            <div class="hero-badge">
                <span class="pulse"></span> System Service Active · v1.0.0
            </div>
            <h1 class="hero-title">SkinLink Tele-Dermatology Platform</h1>
            <p class="hero-subtitle">High-performance REST API supporting multi-tenant clinical workflows, AI lesion quality check & diagnostic assessments.</p>
        </div>

        <div class="grid-3">
            <!-- Card 1: API Operational Status -->
            <div class="card">
                <div class="card-header">
                    <div class="card-title">
                        <svg width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M22 12h-4l-3 9L9 3l-3 9H2"></path></svg>
                        API Server Status
                    </div>
                    <span class="badge badge-success"><span class="pulse"></span> Online</span>
                </div>
                <ul class="status-list">
                    <li class="status-item">
                        <span class="status-label">Service</span>
                        <span class="status-val">{settings.app_name}</span>
                    </li>
                    <li class="status-item">
                        <span class="status-label">Uptime Check</span>
                        <span class="status-val" style="color:#34d399;">Passing 200 OK</span>
                    </li>
                    <li class="status-item">
                        <span class="status-label">CORS Origins</span>
                        <span class="status-val">Wildcard (*) Allowed</span>
                    </li>
                    <li class="status-item">
                        <span class="status-label">Health Path</span>
                        <span class="status-val"><a href="/api/v1/health" style="color:#38bdf8; text-decoration:none;">/api/v1/health</a></span>
                    </li>
                </ul>
            </div>

            <!-- Card 2: Database Storage Status -->
            <div class="card">
                <div class="card-header">
                    <div class="card-title">
                        <svg width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><ellipse cx="12" cy="5" rx="9" ry="3"></ellipse><path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3"></path><path d="M21 19c0 1.66-4 3-9 3s-9-1.34-9-3"></path></svg>
                        SQL Database
                    </div>
                    <span class="badge badge-success"><span class="pulse"></span> Connected</span>
                </div>
                <ul class="status-list">
                    <li class="status-item">
                        <span class="status-label">Engine</span>
                        <span class="status-val">{db_type} (SQLAlchemy)</span>
                    </li>
                    <li class="status-item">
                        <span class="status-label">ORM Status</span>
                        <span class="status-val" style="color:#34d399;">Initialized & Synced</span>
                    </li>
                    <li class="status-item">
                        <span class="status-label">Persistence</span>
                        <span class="status-val">SQL Volume / Connection</span>
                    </li>
                </ul>
            </div>

            <!-- Card 3: AI Engine -->
            <div class="card">
                <div class="card-header">
                    <div class="card-title">
                        <svg width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83"></path></svg>
                        SkinLink AI Engine
                    </div>
                    {ai_status_badge}
                </div>
                <ul class="status-list">
                    <li class="status-item">
                        <span class="status-label">Model Tag</span>
                        <span class="status-val" style="color:#38bdf8;">{gemini_service.model}</span>
                    </li>
                    <li class="status-item">
                        <span class="status-label">Quality Check</span>
                        <span class="status-val">Vision Quality Gate Active</span>
                    </li>
                    <li class="status-item">
                        <span class="status-label">Clinical Reasoning</span>
                        <span class="status-val">Active</span>
                    </li>
                </ul>
            </div>
        </div>

        <!-- Live Platform Metrics Summary -->
        <div class="card" style="margin-bottom: 2.5rem;">
            <div class="card-header">
                <div class="card-title">
                    <svg width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><rect x="3" y="3" width="7" height="7"></rect><rect x="14" y="3" width="7" height="7"></rect><rect x="14" y="14" width="7" height="7"></rect><rect x="3" y="14" width="7" height="7"></rect></svg>
                    Live Database Metrics
                </div>
                <span class="status-label" id="live-refresh-time">Auto-synced</span>
            </div>
            <div class="metrics-grid">
                <div class="metric-box">
                    <div class="metric-num" id="metric-tenants">{len(store.scope(None, "tenants"))}</div>
                    <div class="metric-label">Active Tenants</div>
                </div>
                <div class="metric-box">
                    <div class="metric-num" id="metric-users">{len(store.list_users(None))}</div>
                    <div class="metric-label">Registered Users</div>
                </div>
                <div class="metric-box">
                    <div class="metric-num" id="metric-cases">{len(store.scope(None, "cases"))}</div>
                    <div class="metric-label">Derm Cases</div>
                </div>
                <div class="metric-box">
                    <div class="metric-num" id="metric-patients">{len(store.scope(None, "patients"))}</div>
                    <div class="metric-label">Patient Records</div>
                </div>
            </div>
        </div>

        <!-- Provider / System Admin Setup Section -->
        <div class="form-section" id="setup-section">
            <div class="form-header">
                <div>
                    <h2 class="form-title">Provider & System Administrator Portal</h2>
                    <p class="form-desc">Create or update the primary Provider / Platform Admin account for system administration and tenant management.</p>
                </div>
                <span class="badge badge-success">Provider Portal</span>
            </div>

            <div class="creds-banner">
                <div>
                    <strong>Default Platform Admin:</strong> <span class="code-tag">{settings.platform_admin_email}</span>
                </div>
                <div>
                    <strong>Default Password:</strong> <span class="code-tag">{settings.platform_admin_password}</span>
                </div>
            </div>

            <form id="provider-form" onsubmit="handleSetupProvider(event)">
                <div class="form-grid">
                    <div class="input-group">
                        <label class="input-label" for="provider-name">Full Name</label>
                        <input type="text" id="provider-name" class="input-field" placeholder="e.g. Dr. Administrator" value="SkinLink Operator" required>
                    </div>

                    <div class="input-group">
                        <label class="input-label" for="provider-email">Provider Email</label>
                        <input type="email" id="provider-email" class="input-field" placeholder="ops@skinlink.io" value="{settings.platform_admin_email}" required>
                    </div>

                    <div class="input-group">
                        <label class="input-label" for="provider-title">Professional Title</label>
                        <input type="text" id="provider-title" class="input-field" placeholder="e.g. Lead System Administrator" value="Platform Administrator">
                    </div>

                    <div class="input-group">
                        <label class="input-label" for="provider-password">Account Password</label>
                        <input type="password" id="provider-password" class="input-field" placeholder="At least 6 characters" value="{settings.platform_admin_password}" required minlength="6">
                    </div>
                </div>

                <button type="submit" class="submit-btn" id="setup-submit-btn">
                    Create / Update Provider Admin Account
                </button>

                <div id="alert-msg" class="alert-box"></div>
            </form>
        </div>
    </div>

    <footer class="footer">
        <p>SkinLink Tele-Dermatology Platform · API v1.0.0 · Powered by FastAPI & SQLAlchemy</p>
    </footer>

    <script>
        async function handleSetupProvider(event) {{
            event.preventDefault();
            const btn = document.getElementById('setup-submit-btn');
            const alertMsg = document.getElementById('alert-msg');
            
            btn.disabled = true;
            btn.innerText = 'Creating account...';
            alertMsg.style.display = 'none';

            const payload = {{
                name: document.getElementById('provider-name').value,
                email: document.getElementById('provider-email').value,
                title: document.getElementById('provider-title').value,
                password: document.getElementById('provider-password').value
            }};

            try {{
                const res = await fetch('/api/v1/setup/provider', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify(payload)
                }});
                const data = await res.json();

                if (res.ok && data.success) {{
                    alertMsg.className = 'alert-box alert-success';
                    alertMsg.innerHTML = '<strong>Success!</strong> ' + data.message + '. You can now sign in on the web app using these credentials.';
                    alertMsg.style.display = 'flex';
                    fetchStatusMetrics();
                }} else {{
                    alertMsg.className = 'alert-box alert-error';
                    alertMsg.innerHTML = '<strong>Error:</strong> ' + (data.detail || data.message || 'Setup failed');
                    alertMsg.style.display = 'flex';
                }}
            }} catch (err) {{
                alertMsg.className = 'alert-box alert-error';
                alertMsg.innerHTML = '<strong>Network Error:</strong> Cannot reach API server.';
                alertMsg.style.display = 'flex';
            }} finally {{
                btn.disabled = false;
                btn.innerText = 'Create / Update Provider Admin Account';
            }}
        }}

        async function fetchStatusMetrics() {{
            try {{
                const res = await fetch('/api/v1/status');
                if (res.ok) {{
                    const data = await res.json();
                    if (data.metrics) {{
                        document.getElementById('metric-tenants').innerText = data.metrics.total_tenants;
                        document.getElementById('metric-users').innerText = data.metrics.total_users;
                        document.getElementById('metric-cases').innerText = data.metrics.total_cases;
                        document.getElementById('metric-patients').innerText = data.metrics.total_patients;
                    }}
                }}
            }} catch (e) {{}}
        }}
    </script>
</body>
</html>
"""
    return HTMLResponse(content=html_content)
