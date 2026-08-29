import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.database import init_db
from app.seed import seed_db
from app.routers import admin, ai, auth, cases, drafts, followups, patients, referrals, resources, applications, api_keys, fhir


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


class UploadsCORSMiddleware(BaseHTTPMiddleware):
    """Ensure /uploads/* static files always carry CORS headers."""
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        if request.url.path.startswith("/uploads/"):
            response.headers["Access-Control-Allow-Origin"] = "*"
            response.headers["Access-Control-Allow-Methods"] = "GET, OPTIONS"
            response.headers["Access-Control-Allow-Headers"] = "*"
        return response


app.add_middleware(UploadsCORSMiddleware)

# Serve uploaded images
os.makedirs(settings.upload_dir, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=settings.upload_dir), name="uploads")

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


@app.get("/api/v1/health")
def health():
    return {"status": "ok", "service": settings.app_name}
