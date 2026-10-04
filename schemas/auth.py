from pydantic import BaseModel, Field

from schemas.user import UserOut


class LoginRequest(BaseModel):
    email: str
    password: str = Field(min_length=1, max_length=128)


class AuthSuccessResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut
