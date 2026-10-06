from pydantic import BaseModel


class StatsSummaryOut(BaseModel):
    total_recorded: int  # completed meetings
    meetings_this_week: int
