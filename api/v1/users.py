from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.deps import get_current_user
from config.settings import UPLOAD_DIR
from db.session import get_db
from models.user import User
from schemas.common import PageMeta, PaginatedResponse
from schemas.user import UserAccountListItem, UserMeOut, UserUpdateRequest
from services.pagination import run_paginated
from services.storage import remove_file_if_exists, save_streaming_upload
from utils.ids import new_id

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserMeOut)
def read_me(user: Annotated[User, Depends(get_current_user)]) -> UserMeOut:
    return UserMeOut.model_validate(user)


@router.get("/accounts", response_model=PaginatedResponse[UserAccountListItem])
def list_accounts(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    q: Annotated[str | None, Query(max_length=200)] = None,
) -> PaginatedResponse[UserAccountListItem]:
    stmt = select(User).where(User.id != user.id).order_by(User.created_at.desc())
    if q and q.strip():
        term = f"%{q.strip()}%"
        stmt = stmt.where((User.full_name.ilike(term)) | (User.email.ilike(term)))
    rows, total = run_paginated(db, stmt, skip=skip, limit=limit)
    return PaginatedResponse(
        items=[UserAccountListItem.model_validate(r) for r in rows],
        meta=PageMeta(total=total, skip=skip, limit=limit),
    )


@router.patch("/me", response_model=UserMeOut)
def update_me(
    body: UserUpdateRequest,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> UserMeOut:
    if body.full_name is not None:
        user.full_name = body.full_name.strip()
    if body.default_export_format is not None:
        user.default_export_format = body.default_export_format.strip().lower()
    if body.include_timestamps_default is not None:
        user.include_timestamps_default = body.include_timestamps_default
    db.add(user)
    db.commit()
    db.refresh(user)
    return UserMeOut.model_validate(user)


@router.post("/me/avatar", response_model=UserMeOut)
async def upload_my_avatar(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    file: UploadFile = File(...),
) -> UserMeOut:
    if user.avatar_url and str(user.avatar_url).startswith("user_avatars/"):
        remove_file_if_exists(user.avatar_url)
    ext = Path(file.filename or "photo").suffix or ".jpg"
    rel = f"user_avatars/{user.id}/{new_id()}{ext}"
    save_streaming_upload(file, UPLOAD_DIR / rel)
    user.avatar_url = rel
    db.add(user)
    db.commit()
    db.refresh(user)
    return UserMeOut.model_validate(user)


@router.post("/me/voice", response_model=UserMeOut)
async def upload_my_voice(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    file: UploadFile = File(...),
    duration_seconds: Annotated[int | None, Query(ge=0)] = None,
) -> UserMeOut:
    """Save voice sample to uploads/user_voice/<user_id>/; 400 if file is too small (silent / no mic)."""
    if user.voice_file_path and str(user.voice_file_path).startswith("user_voice/"):
        remove_file_if_exists(user.voice_file_path)
    ext = Path(file.filename or "sample").suffix or ".m4a"
    rel = f"user_voice/{user.id}/{new_id()}{ext}"
    dest = UPLOAD_DIR / rel
    save_streaming_upload(file, dest)
    written = dest.stat().st_size
    if written < 512:
        dest.unlink(missing_ok=True)
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="Voice file is too small — the recording is likely silent. On Android emulator: Extended controls → Microphone → enable host microphone access.",
        )
    user.voice_file_path = rel
    user.has_voice_sample = True
    user.voice_duration_seconds = duration_seconds
    db.add(user)
    db.commit()
    db.refresh(user)
    return UserMeOut.model_validate(user)
