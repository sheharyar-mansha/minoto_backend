from typing import Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class PageMeta(BaseModel):
    total: int
    skip: int = Field(ge=0)
    limit: int = Field(ge=1, le=100)


class PaginatedResponse(BaseModel, Generic[T]):
    items: list[T]
    meta: PageMeta
