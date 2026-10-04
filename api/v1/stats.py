from datetime import date, datetime, time, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from api.deps import get_current_user
from db.session import get_db
from models.meeting import Meeting
from models.user import User
from schemas.stats import StatsSummaryOut

router = APIRouter(prefix="/stats", tags=["stats"])


@router.get("/summary", response_model=StatsSummaryOut)
def summary(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> StatsSummaryOut:
    total_recorded = db.scalar(
        select(func.count()).select_from(Meeting).where(Meeting.status == "completed")
    )
    today = date.today()
    week_start = datetime.combine(today - timedelta(days=today.weekday()), time.min)
    meetings_this_week = db.scalar(
        select(func.count())
        .select_from(Meeting)
        .where(
            Meeting.status == "completed",
            Meeting.conducted_at.isnot(None),
            Meeting.conducted_at >= week_start,
        )
    )
    return StatsSummaryOut(
        total_recorded=int(total_recorded or 0),
        meetings_this_week=int(meetings_this_week or 0),
    )
