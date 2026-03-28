from typing import Any

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session


def run_paginated(
    db: Session,
    stmt: Select[Any],
    *,
    skip: int,
    limit: int,
) -> tuple[list[Any], int]:
    """Run a selectable with offset/limit; return (rows, total_count)."""
    subq = stmt.subquery()
    total = db.scalar(select(func.count()).select_from(subq))
    rows = list(db.execute(stmt.offset(skip).limit(limit)).scalars().all())
    return rows, int(total or 0)
