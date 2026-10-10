from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from app.config import get_settings
from app.models.db_models import Base

settings = get_settings()

# SQLite needs check_same_thread=False since FastAPI's request handlers run
# in a thread pool; this has no effect on Postgres connections.
connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, pool_pre_ping=True, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db() -> None:
    """Create tables and apply lightweight SQLite migrations for added columns."""
    Base.metadata.create_all(bind=engine)
    _migrate_sqlite()


def _migrate_sqlite() -> None:
    """Add new columns to existing SQLite tables if they do not exist."""
    try:
        from sqlalchemy import inspect, text
        inspector = inspect(engine)
        if "job_specification_versions" in inspector.get_table_names():
            columns = {col["name"] for col in inspector.get_columns("job_specification_versions")}
            with engine.begin() as conn:
                if "lifecycle_status" not in columns:
                    conn.execute(text("ALTER TABLE job_specification_versions ADD COLUMN lifecycle_status VARCHAR DEFAULT 'DRAFT'"))
                if "master_context_json" not in columns:
                    conn.execute(text("ALTER TABLE job_specification_versions ADD COLUMN master_context_json JSON"))
                if "parent_specification_version_id" not in columns:
                    conn.execute(text("ALTER TABLE job_specification_versions ADD COLUMN parent_specification_version_id VARCHAR"))
    except Exception as exc:
        # Ignore or log migration failure (e.g. non-SQLite or already exists)
        pass


def get_db() -> Session:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
