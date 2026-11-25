from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from app.config import get_settings
from app.models.db_models import Base
# Import screening models so their tables are registered with Base.metadata
import app.models.screening_models  # noqa: F401

settings = get_settings()

# SQLite needs check_same_thread=False since FastAPI's request handlers run
# in a thread pool; this has no effect on Postgres connections.
connect_args = {"check_same_thread": False, "timeout": 30.0} if settings.database_url.startswith("sqlite") else {}
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
                if "enrichment_report_json" not in columns:
                    conn.execute(text("ALTER TABLE job_specification_versions ADD COLUMN enrichment_report_json JSON"))
                if "s3_enriched_markdown_key" not in columns:
                    conn.execute(text("ALTER TABLE job_specification_versions ADD COLUMN s3_enriched_markdown_key VARCHAR"))
        if "agents" in inspector.get_table_names():
            agent_cols = {col["name"] for col in inspector.get_columns("agents")}
            with engine.begin() as conn:
                if "is_test" not in agent_cols:
                    conn.execute(text("ALTER TABLE agents ADD COLUMN is_test BOOLEAN DEFAULT 0"))

        if "candidate_resumes" in inspector.get_table_names():
            resume_cols = {col["name"] for col in inspector.get_columns("candidate_resumes")}
            with engine.begin() as conn:
                if "file_hash" not in resume_cols:
                    conn.execute(text("ALTER TABLE candidate_resumes ADD COLUMN file_hash VARCHAR(64)"))
                if "parse_quality_check" not in resume_cols:
                    conn.execute(text("ALTER TABLE candidate_resumes ADD COLUMN parse_quality_check JSON"))

        if "candidate_evaluations" in inspector.get_table_names():
            eval_cols = {col["name"] for col in inspector.get_columns("candidate_evaluations")}
            with engine.begin() as conn:
                if "spec_outdated" not in eval_cols:
                    conn.execute(text("ALTER TABLE candidate_evaluations ADD COLUMN spec_outdated BOOLEAN DEFAULT 0"))
                if "evaluator_engine" not in eval_cols:
                    conn.execute(text("ALTER TABLE candidate_evaluations ADD COLUMN evaluator_engine VARCHAR(64) DEFAULT 'deterministic_v1'"))
                if "model_name" not in eval_cols:
                    conn.execute(text("ALTER TABLE candidate_evaluations ADD COLUMN model_name VARCHAR(128)"))
                if "model_version" not in eval_cols:
                    conn.execute(text("ALTER TABLE candidate_evaluations ADD COLUMN model_version VARCHAR(64)"))
                if "prompt_version" not in eval_cols:
                    conn.execute(text("ALTER TABLE candidate_evaluations ADD COLUMN prompt_version VARCHAR(32) DEFAULT 'eval_v2.1'"))
                if "temperature" not in eval_cols:
                    conn.execute(text("ALTER TABLE candidate_evaluations ADD COLUMN temperature FLOAT DEFAULT 0.0"))
                if "seed" not in eval_cols:
                    conn.execute(text("ALTER TABLE candidate_evaluations ADD COLUMN seed INTEGER DEFAULT 42"))
                if "quote_verification_pass" not in eval_cols:
                    conn.execute(text("ALTER TABLE candidate_evaluations ADD COLUMN quote_verification_pass BOOLEAN"))
                if "timeline_observations" not in eval_cols:
                    conn.execute(text("ALTER TABLE candidate_evaluations ADD COLUMN timeline_observations JSON"))
                if "recruiter_override_tier" not in eval_cols:
                    conn.execute(text("ALTER TABLE candidate_evaluations ADD COLUMN recruiter_override_tier VARCHAR(32)"))
                if "recruiter_override_score" not in eval_cols:
                    conn.execute(text("ALTER TABLE candidate_evaluations ADD COLUMN recruiter_override_score INTEGER"))
                if "override_reason" not in eval_cols:
                    conn.execute(text("ALTER TABLE candidate_evaluations ADD COLUMN override_reason TEXT"))
                if "overridden_by" not in eval_cols:
                    conn.execute(text("ALTER TABLE candidate_evaluations ADD COLUMN overridden_by VARCHAR(255)"))
                if "overridden_at" not in eval_cols:
                    conn.execute(text("ALTER TABLE candidate_evaluations ADD COLUMN overridden_at DATETIME"))
    except Exception as exc:
        # Ignore or log migration failure (e.g. non-SQLite or already exists)
        pass


def get_db() -> Session:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# Ensure SQLite tables have latest schema updates even in bare TestClient runs
_migrate_sqlite()

