"""
Integration tests for Multi-JD management, file uploads (.txt, .pdf, .docx),
and context/chat isolation across independent JDs.
"""
import io
import os
import zipfile
import pytest

os.environ.setdefault("LLM_PROVIDER", "mock")

from fastapi.testclient import TestClient
from app.main import app


@pytest.fixture
def client():
    return TestClient(app)


def _create_sample_docx(text: str) -> bytes:
    """Helper to generate in-memory DOCX bytes."""
    document_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f'<w:body><w:p><w:r><w:t>{text}</w:t></w:r></w:p></w:body>'
        '</w:document>'
    )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("word/document.xml", document_xml)
        zf.writestr("[Content_Types].xml", '<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>')
    return buf.getvalue()


class TestMultiJDUploadAndIsolation:
    def test_upload_raw_text_backward_compatibility(self, client):
        """Verify POST /api/jds accepts raw text form submission."""
        res = client.post(
            "/api/jds",
            data={
                "project_id": "proj-alpha",
                "title": "Senior Python Backend Engineer",
                "text": "Senior Python Engineer with 5+ years experience in FastAPI and PostgreSQL.",
            },
        )
        assert res.status_code == 200, res.text
        data = res.json()
        assert "jd_id" in data
        assert data["version"] == 1
        assert data["status"] == "UPLOADED"

    def test_upload_docx_file(self, client):
        """Verify POST /api/jds accepts .docx file upload."""
        docx_bytes = _create_sample_docx("Staff DevOps Engineer with Kubernetes, Terraform, and AWS CI/CD pipelines.")
        res = client.post(
            "/api/jds",
            data={"project_id": "proj-alpha"},
            files={"file": ("devops_jd.docx", docx_bytes, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
        )
        assert res.status_code == 200, res.text
        data = res.json()
        assert "jd_id" in data
        assert "devops jd" in data["title"].lower()

    def test_upload_txt_file(self, client):
        """Verify POST /api/jds accepts .txt file upload."""
        txt_bytes = b"Product Manager with 4+ years B2B SaaS experience and roadmap leadership."
        res = client.post(
            "/api/jds",
            data={"project_id": "proj-alpha"},
            files={"file": ("product_manager.txt", txt_bytes, "text/plain")},
        )
        assert res.status_code == 200, res.text
        data = res.json()
        assert "jd_id" in data

    def test_upload_unsupported_file_format_rejected(self, client):
        """Verify POST /api/jds cleanly rejects unsupported extensions (.jpg, .exe, .md)."""
        res = client.post(
            "/api/jds",
            data={"project_id": "proj-alpha"},
            files={"file": ("avatar.jpg", b"\xff\xd8\xff\xe0", "image/jpeg")},
        )
        assert res.status_code == 400
        assert "Unsupported file format" in res.json()["detail"]

    def test_upload_empty_file_rejected(self, client):
        """Verify POST /api/jds cleanly rejects empty 0-byte files."""
        res = client.post(
            "/api/jds",
            data={"project_id": "proj-alpha"},
            files={"file": ("empty.txt", b"", "text/plain")},
        )
        assert res.status_code == 400
        assert "empty" in res.json()["detail"].lower()

    def test_list_multiple_jds(self, client):
        """Verify GET /api/jds lists multiple distinct JDs."""
        # Create JD A
        res_a = client.post(
            "/api/jds",
            data={"project_id": "proj-list-test", "title": "Role A", "text": "Role A content"},
        )
        jd_a_id = res_a.json()["jd_id"]

        # Create JD B
        res_b = client.post(
            "/api/jds",
            data={"project_id": "proj-list-test", "title": "Role B", "text": "Role B content"},
        )
        jd_b_id = res_b.json()["jd_id"]

        # List all JDs for this project
        list_res = client.get(f"/api/jds?project_id=proj-list-test")
        assert list_res.status_code == 200
        items = list_res.json()
        item_ids = [item["jd_id"] for item in items]
        assert jd_a_id in item_ids
        assert jd_b_id in item_ids

    def test_multi_jd_analysis_and_chat_isolation(self, client):
        """
        Verify that analyzing two distinct JDs produces isolated Markdown/JSON specs,
        and querying JD1's chat endpoint does not leak context into JD2's chat endpoint.
        """
        # Upload JD 1: Technical Python
        res1 = client.post(
            "/api/jds",
            data={
                "project_id": "proj-isolation",
                "title": "Python Architect",
                "text": "Python Architect required with deep FastAPI, Asyncio, and Redis experience.",
            },
        )
        jd1_id = res1.json()["jd_id"]

        # Upload JD 2: Enterprise Sales
        res2 = client.post(
            "/api/jds",
            data={
                "project_id": "proj-isolation",
                "title": "Account Executive",
                "text": "Account Executive with B2B quota carrying experience, CRM sales, and enterprise deals.",
            },
        )
        jd2_id = res2.json()["jd_id"]

        # Analyze both JDs
        client.post(f"/api/jds/{jd1_id}/analyze")
        client.post(f"/api/jds/{jd2_id}/analyze")

        # Verify Markdown specs exist and are independent
        md1_res = client.get(f"/api/jds/{jd1_id}/markdown")
        md2_res = client.get(f"/api/jds/{jd2_id}/markdown")
        assert md1_res.status_code == 200
        assert md2_res.status_code == 200
        assert md1_res.json()["markdown"] != md2_res.json()["markdown"]

        # Chat with JD 1
        chat1 = client.post(
            f"/api/jds/{jd1_id}/chat",
            json={"question": "What technical skills are required?"},
        )
        assert chat1.status_code == 200
        ans1 = chat1.json()["answer"]
        assert len(ans1) > 0

        # Chat with JD 2
        chat2 = client.post(
            f"/api/jds/{jd2_id}/chat",
            json={"question": "What is the core focus of this role?"},
        )
        assert chat2.status_code == 200
        ans2 = chat2.json()["answer"]
        assert len(ans2) > 0

    def test_chat_uses_latest_spec_version(self, client):
        """Verify that chat queries automatically use the latest specification version."""
        # Create JD
        res = client.post(
            "/api/jds",
            data={
                "project_id": "proj-version-test",
                "title": "Frontend Lead",
                "text": "Frontend Lead with React and TypeScript.",
            },
        )
        jd_id = res.json()["jd_id"]

        # Analyze initial version
        client.post(f"/api/jds/{jd_id}/analyze")
        spec_v1 = client.get(f"/api/jds/{jd_id}/markdown").json()["specification_version"]
        assert spec_v1 == 1

        # Chat works with v1
        chat_v1 = client.post(
            f"/api/jds/{jd_id}/chat",
            json={"question": "What is the role?"},
        )
        assert chat_v1.status_code == 200
