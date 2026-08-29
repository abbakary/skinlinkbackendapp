from datetime import datetime, timedelta, timezone
from typing import Annotated, Optional

from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

from app.config import settings
from app.store import store

security = HTTPBearer(auto_error=False)


def create_access_token(user_id: str, tenant_id: Optional[str]) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_expire_minutes)
    payload = {"sub": user_id, "tenantId": tenant_id, "exp": expire}
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


def get_current_user(
    credentials: Annotated[Optional[HTTPAuthorizationCredentials], Depends(security)],
) -> dict:
    if not credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    try:
        payload = jwt.decode(credentials.credentials, settings.secret_key, algorithms=[settings.algorithm])
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    except JWTError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token") from exc
    user = store.get_user(user_id)
    if not user or user.get("status") == "disabled":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user


def get_effective_tenant_id(
    user: Annotated[dict, Depends(get_current_user)],
    x_tenant_id: Annotated[Optional[str], Header(alias="X-Tenant-Id")] = None,
) -> Optional[str]:
    """Resolve tenant scope: org users use their tenant; platform admins may pass X-Tenant-Id."""
    if user["role"] == "platform_admin":
        return x_tenant_id
    return user.get("tenantId")


def require_tenant(
    user: Annotated[dict, Depends(get_current_user)],
    x_tenant_id: Annotated[Optional[str], Header(alias="X-Tenant-Id")] = None,
) -> str:
    tenant_id = get_effective_tenant_id(user, x_tenant_id)
    if not tenant_id:
        raise HTTPException(status_code=400, detail="Tenant context required")
    return tenant_id


def require_platform_admin(user: Annotated[dict, Depends(get_current_user)]) -> dict:
    if user["role"] != "platform_admin":
        raise HTTPException(status_code=403, detail="Platform admin access required")
    return user


def require_roles(allowed_roles: list[str]):
    def _checker(user: Annotated[dict, Depends(get_current_user)]) -> dict:
        if user.get("role") not in allowed_roles:
            raise HTTPException(
                status_code=403,
                detail=f"Access restricted to roles: {', '.join(allowed_roles)}",
            )
        return user
    return _checker
