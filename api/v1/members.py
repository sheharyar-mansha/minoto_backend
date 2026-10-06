"""Members = the reusable Contact roster (non-login people who attend meetings)."""

from datetime import datetime
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from api.deps import get_current_user
from config.settings import UPLOAD_DIR
from db.session import get_db
from models.contact import Contact
from models.user import User
from pipeline.enroll import enroll_contact_voice
from schemas.member import MemberCreate, MemberListItem, MemberOut, MemberUpdate
from services.storage import remove_file_if_exists, save_streaming_upload
from utils.ids import new_id

router = APIRouter(prefix="/members", tags=["members"])

# Below this many bytes the recording is almost certainly silent / no mic.
_MIN_VOICE_BYTES = 512


def _get_contact_or_404(db: Session, member_id: str) -> Contact:
    contact = db.get(Contact, member_id)
    if contact is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Member not found")
    return contact


def _email_in_use(db: Session, email: str, *, exclude_id: str | None = None) -> bool:
    stmt = select(Contact.id).where(func.lower(Contact.email) == email)
    if exclude_id is not None:
        stmt = stmt.where(Contact.id != exclude_id)
    return db.scalars(stmt).first() is not None


@router.get("", response_model=list[MemberListItem])
def list_members(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    q: Annotated[str | None, Query(max_length=200)] = None,
) -> list[MemberListItem]:
    stmt = select(Contact).order_by(Contact.name.asc(), Contact.created_at.asc())
    if q and q.strip():
        term = f"%{q.strip()}%"
        stmt = stmt.where((Contact.name.ilike(term)) | (Contact.email.ilike(term)))
    rows = db.scalars(stmt.offset(skip).limit(limit)).all()
    return [MemberListItem.model_validate(r) for r in rows]


@router.post("", response_model=MemberOut, status_code=status.HTTP_201_CREATED)
def create_member(
    body: MemberCreate,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> MemberOut:
    email = str(body.email).strip().lower()
    if _email_in_use(db, email):
        raise HTTPException(status.HTTP_409_CONFLICT, detail="A member with this email already exists")
    contact = Contact(id=new_id(), name=body.name.strip(), email=email)
    db.add(contact)
    db.commit()
    db.refresh(contact)
    return MemberOut.model_validate(contact)


@router.get("/{member_id}", response_model=MemberOut)
def get_member(
    member_id: str,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> MemberOut:
    return MemberOut.model_validate(_get_contact_or_404(db, member_id))


@router.patch("/{member_id}", response_model=MemberOut)
def update_member(
    member_id: str,
    body: MemberUpdate,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> MemberOut:
    contact = _get_contact_or_404(db, member_id)
    if body.name is not None:
        contact.name = body.name.strip()
    if body.email is not None:
        email = str(body.email).strip().lower()
        if _email_in_use(db, email, exclude_id=contact.id):
            raise HTTPException(status.HTTP_409_CONFLICT, detail="A member with this email already exists")
        contact.email = email
    db.add(contact)
    db.commit()
    db.refresh(contact)
    return MemberOut.model_validate(contact)


@router.delete("/{member_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_member(
    member_id: str,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> None:
    contact = _get_contact_or_404(db, member_id)
    remove_file_if_exists(contact.voice_file_path)
    db.delete(contact)
    db.commit()


@router.post("/{member_id}/voice", response_model=MemberOut)
async def upload_member_voice(
    member_id: str,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    file: UploadFile = File(...),
    duration_seconds: Annotated[int | None, Query(ge=0)] = None,
) -> MemberOut:
    """Save/replace a member's guided voice intro and run enrollment.

    Phase 2: the audio + duration are stored and `has_voice_sample` is set, but
    the embedding / spoken name come back empty from the stub enroller.
    """
    contact = _get_contact_or_404(db, member_id)

    # Replace any previous sample so we never leak orphaned files.
    remove_file_if_exists(contact.voice_file_path)

    ext = Path(file.filename or "sample").suffix or ".m4a"
    rel = f"contact_voice/{contact.id}/{new_id()}{ext}"
    dest = UPLOAD_DIR / rel
    save_streaming_upload(file, dest)
    if dest.stat().st_size < _MIN_VOICE_BYTES:
        dest.unlink(missing_ok=True)
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="Voice file is too small — the recording is likely silent.",
        )

    enrollment = enroll_contact_voice(dest)

    contact.voice_file_path = rel
    contact.voice_duration_seconds = duration_seconds
    contact.voice_recorded_at = datetime.now()
    contact.has_voice_sample = True
    contact.voice_embedding_json = enrollment.get("embedding_json")
    contact.spoken_name = enrollment.get("spoken_name")
    contact.spoken_name_source = enrollment.get("spoken_name_source")
    db.add(contact)
    db.commit()
    db.refresh(contact)
    return MemberOut.model_validate(contact)


@router.get("/{member_id}/voice")
def download_member_voice(
    member_id: str,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> FileResponse:
    """Stream the stored voice sample (auth required), or 404 if none."""
    contact = _get_contact_or_404(db, member_id)
    if not contact.has_voice_sample or not contact.voice_file_path:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="No voice sample for this member")
    path = UPLOAD_DIR / contact.voice_file_path
    if not path.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Voice file is missing")
    return FileResponse(path, filename=path.name)
