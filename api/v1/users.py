from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy.orm import Session

from api.deps import get_current_user
from config.settings import UPLOAD_DIR
from db.session import get_db
from models.user import User
from schemas.user import UserMeOut, UserUpdateRequest
from services.storage import remove_file_if_exists, save_streaming_upload
from utils.ids import new_id

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserMeOut)
def read_me(user: Annotated[User, Depends(get_current_user)]) -> UserMeOut:
    return UserMeOut.model_validate(user)


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
