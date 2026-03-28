from typing import Annotated

from fastapi import Depends, HTTPException, Query, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from db.session import get_db
from models.meeting import Meeting
from models.user import User
from services.security import decode_token_subject

security = HTTPBearer(auto_error=False)


def pagination(
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> tuple[int, int]:
    return skip, limit


def get_current_user(
    db: Annotated[Session, Depends(get_db)],
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(security)],
) -> User:
    if creds is None or creds.scheme.lower() != "bearer":
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    uid = decode_token_subject(creds.credentials)
    if uid is None:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user = db.get(User, uid)
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user


def get_meeting_for_user(
    meeting_id: str,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> Meeting:
    m = db.get(Meeting, meeting_id)
    if m is None or m.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Meeting not found")
    return m
