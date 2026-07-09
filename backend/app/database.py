from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import get_settings

settings = get_settings()
connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _ensure_sqlite_generation_task_columns() -> None:
    """Small MVP migration for local SQLite databases created before progress fields existed."""
    if not settings.database_url.startswith("sqlite"):
        return

    with engine.begin() as connection:
        rows = connection.exec_driver_sql("PRAGMA table_info(generation_tasks)").fetchall()
        columns = {row[1] for row in rows}
        if not columns:
            return
        if "progress" not in columns:
            connection.exec_driver_sql("ALTER TABLE generation_tasks ADD COLUMN progress INTEGER NOT NULL DEFAULT 0")
        if "current_step" not in columns:
            connection.exec_driver_sql("ALTER TABLE generation_tasks ADD COLUMN current_step VARCHAR(120)")


def init_db() -> None:
    from app import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    _ensure_sqlite_generation_task_columns()
