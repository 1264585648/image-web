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


def _sqlite_columns(table_name: str) -> set[str]:
    rows = engine.connect().exec_driver_sql(f"PRAGMA table_info({table_name})").fetchall()
    return {row[1] for row in rows}


def _ensure_sqlite_generation_task_columns() -> None:
    """Small MVP migration for local SQLite databases created before progress/auth fields existed."""
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
        if "user_id" not in columns:
            connection.exec_driver_sql("ALTER TABLE generation_tasks ADD COLUMN user_id VARCHAR(36)")
            connection.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_generation_tasks_user_id ON generation_tasks(user_id)")


def _ensure_sqlite_source_image_columns() -> None:
    """Small MVP migration for local SQLite databases created before auth fields existed."""
    if not settings.database_url.startswith("sqlite"):
        return

    with engine.begin() as connection:
        rows = connection.exec_driver_sql("PRAGMA table_info(source_images)").fetchall()
        columns = {row[1] for row in rows}
        if not columns:
            return
        if "user_id" not in columns:
            connection.exec_driver_sql("ALTER TABLE source_images ADD COLUMN user_id VARCHAR(36)")
            connection.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_source_images_user_id ON source_images(user_id)")


def init_db() -> None:
    from app import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    _ensure_sqlite_generation_task_columns()
    _ensure_sqlite_source_image_columns()
