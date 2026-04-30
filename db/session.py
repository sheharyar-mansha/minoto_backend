from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.exc import IllegalStateChangeError
from sqlalchemy.orm import Session, sessionmaker

from config.settings import settings

_connect_args: dict = {}
if settings.DATABASE_URL.startswith("sqlite"):
    _connect_args["check_same_thread"] = False

engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    connect_args=_connect_args,
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        # Ctrl+C / server shutdown can cancel requests while a sync DB dependency is
        # still opening a connection; closing then raises IllegalStateChangeError.
        try:
            db.close()
        except IllegalStateChangeError:
            pass
