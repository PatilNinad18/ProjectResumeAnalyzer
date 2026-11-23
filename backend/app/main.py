from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router as jds_router
from app.api.screening_routes import router as screening_router
from app.db import init_db

app = FastAPI(
    title="JD Understanding Agent API",
    version="1.0.0",
    description="Converts raw Job Descriptions into a canonical Candidate Evaluation Specification (MD + JSON).",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten to the frontend origin in production
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(jds_router)
app.include_router(screening_router)


@app.on_event("startup")
def on_startup() -> None:
    # In production, use Alembic migrations instead of create_all().
    init_db()
    from app.services.batch_queue import jd_batch_queue
    jd_batch_queue.start()
    from app.workers.screening_worker import screening_queue
    screening_queue.start()


@app.get("/health")
def health():
    return {"status": "ok"}
