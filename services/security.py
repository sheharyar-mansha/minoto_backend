from datetime import UTC, datetime, timedelta

from jose import JWTError, jwt
from passlib.context import CryptContext

from config.settings import settings

_pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(plain: str) -> str:
    return _pwd.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return _pwd.verify(plain, hashed)


def create_access_token(subject_user_id: str, *, typ: str | None = None) -> str:
    expire = datetime.now(UTC) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    payload: dict = {"sub": subject_user_id, "exp": expire}
    if typ is not None:
        # Principal type: absent/"owner" → the owner User; "member" → a Contact.
        payload["typ"] = typ
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_token_subject(token: str) -> str | None:
    claims = decode_token_claims(token)
    sub = claims.get("sub") if claims else None
    return str(sub) if sub is not None else None


def decode_token_claims(token: str) -> dict | None:
    """Decode and verify a token, returning its claims (or None if invalid)."""
    try:
        return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
    except JWTError:
        return None
