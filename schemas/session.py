from pydantic import BaseModel, Field, model_validator


class LiveSessionUpsert(BaseModel):
    meeting_id: str = Field(min_length=1)
    title: str = Field(min_length=1, max_length=500)
    elapsed_seconds: int = Field(ge=0)
    is_paused: bool
    running_since_ms: int | None = None
    total_target_seconds: int = Field(ge=0)

    @model_validator(mode="after")
    def _validate_running_state(self) -> "LiveSessionUpsert":
        if self.is_paused and self.running_since_ms is not None:
            raise ValueError("running_since_ms must be null when is_paused is true")
        if not self.is_paused and self.running_since_ms is None:
            raise ValueError("running_since_ms is required when is_paused is false")
        return self


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
