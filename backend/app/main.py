from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router as jds_router
from app.api.screening_routes import router as screening_router
from app.db import init_db
from app.config import get_settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    from app.services.batch_queue import jd_batch_queue
    from app.workers.screening_worker import screening_queue

    init_db()
    jd_batch_queue.start()
    screening_queue.start()
    try:
        yield
    finally:
        screening_queue.stop()


app = FastAPI(
    title="JD Understanding Agent API",
    version="1.0.0",
    description="Converts raw Job Descriptions into a canonical Candidate Evaluation Specification (MD + JSON).",
    lifespan=lifespan,
)

frontend_origins = ["http://localhost:3000", "http://127.0.0.1:3000"]
if configured_origin := get_settings().frontend_origin:
    frontend_origins.append(configured_origin)
app.add_middleware(
    CORSMiddleware,
    allow_origins=frontend_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(jds_router)
app.include_router(screening_router)


@app.get("/health")
def health():
    return {"status": "ok"}
