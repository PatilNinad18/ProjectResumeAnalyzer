"""Measure a synthetic batch through upload, SQLite, the screening worker, and polling."""
from __future__ import annotations

import argparse
import io
import json
import logging
import math
import os
import platform
import sys
import textwrap
import time
import zipfile
from collections import Counter
from pathlib import Path
from tempfile import TemporaryDirectory
from xml.sax.saxutils import escape

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tests.benchmark_dataset import BENCHMARK_CANDIDATES, TARGET_JOB_SPEC


def _synthetic_docx(text: str) -> bytes:
    buf = io.BytesIO()
    paragraphs = "".join(f"<w:p><w:r><w:t>{escape(line)}</w:t></w:r></w:p>" for line in text.splitlines())
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as doc:
        doc.writestr("word/document.xml", (
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            f"<w:body>{paragraphs}</w:body></w:document>"
        ))
    return buf.getvalue()


def _synthetic_pdf(text: str, case_id: str) -> bytes:
    from pypdf import PdfWriter
    from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

    writer = PdfWriter()
    writer.add_metadata({"/Subject": case_id})
    page = writer.add_blank_page(width=612, height=792)
    if text:
        font = DictionaryObject({NameObject("/Type"): NameObject("/Font"),
                                 NameObject("/Subtype"): NameObject("/Type1"),
                                 NameObject("/BaseFont"): NameObject("/Helvetica")})
        page[NameObject("/Resources")] = DictionaryObject({
            NameObject("/Font"): DictionaryObject({NameObject("/F1"): font}),
        })
        lines = [part for line in text.splitlines() for part in (textwrap.wrap(line, 100) or [""])]
        commands = ["BT /F1 10 Tf 12 TL 55 750 Td"]
        for line in lines:
            line = line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
            commands.append(f"({line}) Tj T*")
        stream = DecodedStreamObject()
        stream.set_data("\n".join([*commands, "ET"]).encode("latin-1", errors="replace"))
        page.replace_contents(stream)
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def _files(count: int):
    readable = [
        row["text"] for row in BENCHMARK_CANDIDATES
        if row["category"] != "PARSE_FAILED"
    ]
    for index in range(count):
        case_id = f"bench-{index + 1:04}"
        text = f"{readable[index % len(readable)]}\n\nBenchmark reference {case_id}\n"
        slot = index % 10
        if slot < 5:
            yield "files", (f"{case_id}.pdf", _synthetic_pdf("" if index % 50 == 0 else text, case_id), "application/pdf")
        elif slot < 8:
            yield "files", (f"{case_id}.docx", _synthetic_docx(text), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
        else:
            yield "files", (f"{case_id}.txt", text.encode("utf-8"), "text/plain")


def _percentile(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    return round(sorted(values)[math.ceil(len(values) * percentile) - 1], 3)


def run(count: int, poll_interval: float, timeout: float) -> dict:
    with TemporaryDirectory(prefix="resumeta-benchmark-") as temp:
        root = Path(temp)
        os.environ.update(
            DATABASE_URL=f"sqlite:///{(root / 'benchmark.db').as_posix()}",
            RESUME_STORAGE_DIR=str(root / "resumes"),
            LOCAL_STORAGE_PATH=str(root / "storage"),
            STORAGE_BACKEND="local",
            LLM_PROVIDER="mock",
            DISABLE_SQLALCHEMY_CEXT="1",
        )
        from fastapi.testclient import TestClient
        from sqlalchemy import text

        from app.db import SessionLocal, engine, init_db
        from app.main import app
        from app.models.db_models import JDLifecycleStatusEnum, JobDescription, JobDescriptionVersion, JobSpecificationVersion, Project, User
        from app.models.screening_models import CandidateEvaluation
        from app.services.resume.evaluator import EVALUATOR_ENGINE

        init_db()
        with SessionLocal() as db:
            owner = User(email="screening-benchmark@example.test")
            db.add(owner)
            db.flush()
            project = Project(name="Isolated screening benchmark", owner_id=owner.id)
            db.add(project)
            db.flush()
            jd = JobDescription(project_id=project.id, title=TARGET_JOB_SPEC["title"])
            db.add(jd)
            db.flush()
            revision = JobDescriptionVersion(job_description_id=jd.id, version=1, s3_raw_key="synthetic.txt", raw_text_checksum="synthetic")
            db.add(revision)
            db.flush()
            db.add(JobSpecificationVersion(
                job_description_version_id=revision.id, specification_version=1,
                lifecycle_status=JDLifecycleStatusEnum.FINALIZED, s3_json_key="synthetic.json", s3_markdown_key="synthetic.md",
                canonical_json=TARGET_JOB_SPEC, prompt_version="synthetic", model_version="fixture",
            ))
            base = f"/api/jds/{jd.id}/resumes"
            db.commit()
            journal_mode = db.execute(text("PRAGMA journal_mode")).scalar()

        files = list(_files(count))
        with TestClient(app) as client:
            start = time.perf_counter()
            uploaded = client.post(base, files=files)
            uploaded.raise_for_status()
            uploads = uploaded.json()
            if uploads["failed"] or len(uploads["uploaded"]) != count:
                raise RuntimeError(f"Upload accepted {len(uploads['uploaded'])} of {count}: {uploads['failed']}")
            after_upload = time.perf_counter()

            queued = client.post(f"{base}/screen")
            queued.raise_for_status()
            if queued.json()["queued_count"] != count:
                raise RuntimeError("The screening endpoint did not queue the entire benchmark batch.")
            after_queue = time.perf_counter()

            poll_durations = []
            while True:
                poll_start = time.perf_counter()
                response = client.get(f"{base}/status")
                response.raise_for_status()
                poll_durations.append(time.perf_counter() - poll_start)
                rows = response.json()["candidates"]
                if len(rows) == count and all(row["status"] not in {"QUEUED", "ANALYZING"} for row in rows):
                    break
                if time.perf_counter() - after_queue > timeout:
                    raise TimeoutError("The screening batch did not finish before the measurement timeout.")
                time.sleep(poll_interval)
            end = time.perf_counter()

        with SessionLocal() as db:
            worker_times = [
                (row.completed_at - row.started_at).total_seconds()
                for row in db.query(CandidateEvaluation).all()
                if row.completed_at and row.started_at
            ]
        engine.dispose()

    if len(worker_times) != count:
        raise RuntimeError(f"Found {len(worker_times)} timed worker records for {count} candidates.")
    return {
        "dataset": "synthetic",
        "candidates": count,
        "formats": dict(Counter(Path(file[1][0]).suffix[1:] for file in files)),
        "outcomes": dict(Counter(row["status"] for row in rows)),
        "outcomes_by_format": {
            fmt: dict(Counter(row["status"] for row in rows if row["filename"].endswith(f".{fmt}")))
            for fmt in ("pdf", "docx", "txt")
        },
        "environment": {
            "os": platform.platform(), "processor": platform.processor(), "logical_cpus": os.cpu_count(),
            "python": platform.python_version(), "sqlite": journal_mode, "workers": 1, "evaluator": EVALUATOR_ENGINE,
            "poll_endpoint": "/resumes/status",
        },
        "seconds": {
            "batch_upload": round(after_upload - start, 3),
            "queue_request": round(after_queue - after_upload, 3),
            "after_queue_until_observed_complete": round(end - after_queue, 3),
            "total": round(end - start, 3),
            "worker_p50_per_resume": _percentile(worker_times, .50),
            "worker_p95_per_resume": _percentile(worker_times, .95),
            "poll_request_p95": _percentile(poll_durations, .95),
        },
        "resumes_per_second": round(count / (end - start), 2),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, default=200)
    parser.add_argument("--poll-interval", type=float, default=.25)
    parser.add_argument("--timeout", type=float, default=180)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.count < 1 or args.poll_interval <= 0 or args.timeout <= 0:
        parser.error("Count, poll interval, and timeout must be positive.")
    logging.getLogger("jd_agent.screening_worker").setLevel(logging.WARNING)
    logging.getLogger("jd_agent.evaluator").setLevel(logging.ERROR)
    result = run(args.count, args.poll_interval, args.timeout)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    if result["outcomes"].get("FAILED"):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
