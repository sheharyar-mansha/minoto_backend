from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from db.session import get_db
from models.user import User
from schemas.auth import AuthSuccessResponse, LoginRequest
from schemas.user import UserOut
from services.security import create_access_token, verify_password

router = APIRouter()


@router.post("/login", response_model=AuthSuccessResponse)
def login(body: LoginRequest, db: Session = Depends(get_db)) -> AuthSuccessResponse:
    """Log the single owner in. There is no signup — the owner is seeded."""
    email = body.email.strip().lower()
    user = db.scalars(select(User).where(User.email == email)).first()
    if user is None or not verify_password(body.password, user.hashed_password):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )
    token = create_access_token(user.id)
    return AuthSuccessResponse(access_token=token, user=UserOut.model_validate(user))
