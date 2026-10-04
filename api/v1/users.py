from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from api.deps import get_current_user
from db.session import get_db
from models.user import User
from schemas.user import UserMeOut, UserUpdateRequest

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
    """Update the owner's profile name and export preferences."""
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
