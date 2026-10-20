import secrets
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.deps import get_current_member
from db.session import get_db
from models.contact import Contact
from models.user import User
from schemas.auth import (
    AuthSuccessResponse,
    LoginRequest,
    PrincipalOut,
    SetPasswordRequest,
)
from schemas.user import UserOut
from services.security import create_access_token, hash_password, verify_password
from utils.passwords import password_policy_error

router = APIRouter()


def _owner_principal(user: User) -> PrincipalOut:
    return PrincipalOut(role="owner", **UserOut.model_validate(user).model_dump())


def _member_principal(contact: Contact) -> PrincipalOut:
    return PrincipalOut(
        id=contact.id, email=contact.email, full_name=contact.name, role="member"
    )


def _member_success(contact: Contact) -> AuthSuccessResponse:
    token = create_access_token(contact.id, typ="member")
    return AuthSuccessResponse(
        access_token=token,
        role="member",
        must_set_password=bool(contact.must_set_password),
        user=_member_principal(contact),
    )


@router.post("/login", response_model=AuthSuccessResponse)
def login(body: LoginRequest, db: Session = Depends(get_db)) -> AuthSuccessResponse:
    """Log in the owner, or a read-only member account (feature-flagged in the app)."""
    email = body.email.strip().lower()

    # 1) The owner.
    user = db.scalars(select(User).where(User.email == email)).first()
    if user is not None and verify_password(body.password, user.hashed_password):
        return AuthSuccessResponse(
            access_token=create_access_token(user.id),
            role="owner",
            must_set_password=False,
            user=_owner_principal(user),
        )

    # 2) A member account.
    contact = db.scalars(select(Contact).where(Contact.email == email)).first()
    if contact is not None:
        # First login (or after a reset): the one-time temp password.
        if (
            contact.must_set_password
            and contact.temp_password
            and secrets.compare_digest(body.password, contact.temp_password)
        ):
            return _member_success(contact)
        # Normal login with the member's own password.
        if contact.hashed_password and not contact.must_set_password and verify_password(
            body.password, contact.hashed_password
        ):
            return _member_success(contact)

    raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")


@router.post("/set-password", response_model=AuthSuccessResponse)
def set_password(
    body: SetPasswordRequest,
    member: Annotated[Contact, Depends(get_current_member)],
    db: Annotated[Session, Depends(get_db)],
) -> AuthSuccessResponse:
    """Member sets their own password on first login (replaces the temp password)."""
    if body.new_password != body.confirm_password:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Passwords do not match")
    policy = password_policy_error(body.new_password)
    if policy:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=policy)
    member.hashed_password = hash_password(body.new_password)
    member.temp_password = None
    member.must_set_password = False
    member.password_set_at = datetime.now()
    db.add(member)
    db.commit()
    db.refresh(member)
    return _member_success(member)


@router.post("/change-password", response_model=AuthSuccessResponse)
def change_password(
    body: SetPasswordRequest,
    member: Annotated[Contact, Depends(get_current_member)],
    db: Annotated[Session, Depends(get_db)],
) -> AuthSuccessResponse:
    """Member changes their password from the profile (already authenticated)."""
    if member.must_set_password or not member.hashed_password:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Set your password first")
    if body.new_password != body.confirm_password:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Passwords do not match")
    policy = password_policy_error(body.new_password)
    if policy:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=policy)
    member.hashed_password = hash_password(body.new_password)
    member.password_set_at = datetime.now()
    db.add(member)
    db.commit()
    db.refresh(member)
    return _member_success(member)
