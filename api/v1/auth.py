from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from db.session import get_db
from models.user import User
from schemas.auth import AuthSuccessResponse, LoginRequest, RegisterRequest
from schemas.user import UserOut
from services.security import create_access_token, hash_password, verify_password
from utils.ids import new_id

router = APIRouter()


@router.post("/register", response_model=AuthSuccessResponse, status_code=status.HTTP_201_CREATED)
def register(body: RegisterRequest, db: Session = Depends(get_db)) -> AuthSuccessResponse:
    email = body.email.strip().lower()
    existing = db.scalars(select(User).where(User.email == email)).first()
    if existing is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="Email already registered")
    user = User(
        id=new_id(),
        email=email,
        full_name=body.full_name.strip(),
        hashed_password=hash_password(body.password),
        role="participant",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    token = create_access_token(user.id)
    return AuthSuccessResponse(access_token=token, user=UserOut.model_validate(user))


@router.post("/login", response_model=AuthSuccessResponse)
def login(body: LoginRequest, db: Session = Depends(get_db)) -> AuthSuccessResponse:
    email = body.email.strip().lower()
    user = db.scalars(select(User).where(User.email == email)).first()
    if user is None or not verify_password(body.password, user.hashed_password):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )
    token = create_access_token(user.id)
    return AuthSuccessResponse(access_token=token, user=UserOut.model_validate(user))
