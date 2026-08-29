from typing import Annotated
import uuid

from fastapi import APIRouter, Depends

from app.auth import get_current_user
from app.store import store

router = APIRouter(prefix="/drafts", tags=["drafts"])


@router.get("")
def list_drafts(user: Annotated[dict, Depends(get_current_user)]):
    return store.get_drafts(user["id"])


@router.post("")
def save_draft(payload: dict, user: Annotated[dict, Depends(get_current_user)]):
    draft_id = payload.get("id") or f"draft_{uuid.uuid4().hex[:8]}"
    draft = store.save_draft(user["id"], {**payload, "id": draft_id})
    return draft


@router.delete("/{draft_id}")
def delete_draft(draft_id: str, user: Annotated[dict, Depends(get_current_user)]):
    store.delete_draft(user["id"], draft_id)
    return {"ok": True}
