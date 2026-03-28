from pydantic import BaseModel, Field


class LiveSessionUpsert(BaseModel):
    meeting_id: str = Field(min_length=1)
    title: str = Field(min_length=1, max_length=500)
    elapsed_seconds: int = Field(ge=0)
    is_paused: bool
    running_since_ms: int | None = None
    total_target_seconds: int = Field(ge=0)


class LiveSessionOut(BaseModel):
    meeting_id: str
    title: str
    elapsed_seconds: int
    is_paused: bool
    running_since_ms: int | None
    total_target_seconds: int


class StatsSummaryOut(BaseModel):
    meetings_this_week: int
    total_recorded: int
