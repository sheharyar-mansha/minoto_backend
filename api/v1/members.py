from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from api.deps import get_current_user, pagination
from config.settings import UPLOAD_DIR
from db.session import get_db
from models.member import Member
from models.user import User
from schemas.common import PageMeta, PaginatedResponse
from schemas.member import MemberCreate, MemberOut, MemberUpdate
from services.pagination import run_paginated
from services.storage import remove_file_if_exists, save_streaming_upload
from utils.ids import new_id

router = APIRouter(prefix="/members", tags=["members"])


@router.get("", response_model=PaginatedResponse[MemberOut])
def list_members(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    page: Annotated[tuple[int, int], Depends(pagination)],
    q: Annotated[str | None, Query(max_length=200)] = None,
    saved_to_directory: Annotated[bool | None, Query()] = None,
) -> PaginatedResponse[MemberOut]:
    skip, limit = page
    stmt = select(Member).where(Member.user_id == user.id).order_by(Member.name)
    if q:
        term = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(Member.name.ilike(term), Member.email.ilike(term)),
        )
    if saved_to_directory is not None:
        stmt = stmt.where(Member.saved_to_directory == saved_to_directory)
    rows, total = run_paginated(db, stmt, skip=skip, limit=limit)
    return PaginatedResponse(
        items=[MemberOut.model_validate(r) for r in rows],
        meta=PageMeta(total=total, skip=skip, limit=limit),
    )


@router.post("", response_model=MemberOut, status_code=status.HTTP_201_CREATED)
def create_member(
    body: MemberCreate,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> MemberOut:
    m = Member(
        id=new_id(),
        user_id=user.id,
        name=body.name.strip(),
        email=body.email.strip().lower(),
        role=body.role.strip() if body.role else None,
        member_since=body.member_since,
        saved_to_directory=body.saved_to_directory,
    )
    db.add(m)
    db.commit()
    db.refresh(m)
    return MemberOut.model_validate(m)


@router.get("/{member_id}", response_model=MemberOut)
def get_member(
    member_id: str,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> MemberOut:
    m = db.get(Member, member_id)
    if m is None or m.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Member not found")
    return MemberOut.model_validate(m)


@router.patch("/{member_id}", response_model=MemberOut)
def update_member(
    member_id: str,
    body: MemberUpdate,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> MemberOut:
    m = db.get(Member, member_id)
    if m is None or m.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Member not found")
    data = body.model_dump(exclude_unset=True)
    if "email" in data and data["email"] is not None:
        data["email"] = str(data["email"]).strip().lower()
    if "name" in data and data["name"] is not None:
        data["name"] = str(data["name"]).strip()
    if "role" in data and data["role"] is not None:
        data["role"] = str(data["role"]).strip()
    for k, v in data.items():
        setattr(m, k, v)
    db.add(m)
    db.commit()
    db.refresh(m)
    return MemberOut.model_validate(m)


@router.delete("/{member_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_member(
    member_id: str,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> None:
    m = db.get(Member, member_id)
    if m is None or m.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Member not found")
    remove_file_if_exists(m.voice_file_path)
    if m.avatar_url and m.avatar_url.startswith("avatars/"):
        remove_file_if_exists(m.avatar_url)
    db.delete(m)
    db.commit()


@router.post("/{member_id}/voice", response_model=MemberOut)
async def upload_voice(
    member_id: str,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    file: UploadFile = File(...),
    duration_seconds: Annotated[int | None, Query(ge=0)] = None,
) -> MemberOut:
    m = db.get(Member, member_id)
    if m is None or m.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Member not found")
    remove_file_if_exists(m.voice_file_path)
    ext = Path(file.filename or "sample").suffix or ".m4a"
    rel = f"voice/{user.id}/{member_id}/{new_id()}{ext}"
    save_streaming_upload(file, UPLOAD_DIR / rel)
    m.voice_file_path = rel
    m.has_voice_sample = True
    m.voice_duration_seconds = duration_seconds
    db.add(m)
    db.commit()
    db.refresh(m)
    return MemberOut.model_validate(m)


@router.post("/{member_id}/avatar", response_model=MemberOut)
async def upload_avatar(
    member_id: str,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    file: UploadFile = File(...),
) -> MemberOut:
    m = db.get(Member, member_id)
    if m is None or m.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Member not found")
    if m.avatar_url and str(m.avatar_url).startswith("avatars/"):
        remove_file_if_exists(m.avatar_url)
    ext = Path(file.filename or "photo").suffix or ".jpg"
    rel = f"avatars/{user.id}/{member_id}/{new_id()}{ext}"
    save_streaming_upload(file, UPLOAD_DIR / rel)
    m.avatar_url = rel
    db.add(m)
    db.commit()
    db.refresh(m)
    return MemberOut.model_validate(m)
