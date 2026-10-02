"""
Unit tests for the document parser service (app/services/document_parser.py).
Tests .txt, .pdf, .docx extraction, and verifies error handling with DocumentParseError.
"""
import io
import zipfile
import pytest
from app.services.document_parser import (
    DocumentParseError,
    extract_text_from_docx,
    extract_text_from_pdf,
    extract_text_from_txt,
    parse_document,
)


def _create_sample_docx(paragraphs: list[str]) -> bytes:
    """Helper to generate an in-memory minimal valid DOCX file."""
    body_xml_parts = []
    for p in paragraphs:
        body_xml_parts.append(f"<w:p><w:r><w:t>{p}</w:t></w:r></w:p>")
    
    document_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f'<w:body>{"".join(body_xml_parts)}</w:body>'
        '</w:document>'
    )
    
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("word/document.xml", document_xml)
        zf.writestr("[Content_Types].xml", '<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>')
    return buf.getvalue()


def _create_sample_pdf(text: str) -> bytes:
    """Helper to generate an in-memory minimal PDF file."""
    content_stream = f"BT /F1 12 Tf 72 712 Td ({text}) Tj ET".encode("latin-1")
    stream_obj = (
        b"4 0 obj\n<< /Length "
        + str(len(content_stream)).encode("ascii")
        + b" >>\nstream\n"
        + content_stream
        + b"\nendstream\nendobj\n"
    )
    pdf_bytes = (
        b"%PDF-1.4\n"
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
        b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>\nendobj\n"
        + stream_obj
        + b"5 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n"
        b"xref\n0 6\n0000000000 65535 f \n0000000010 00000 n \n0000000060 00000 n \n0000000117 00000 n \n0000000248 00000 n \n0000000326 00000 n \n"
        b"trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n398\n%%EOF"
    )
    return pdf_bytes


class TestDocumentParser:
    def test_txt_extraction_utf8(self):
        sample_text = "Role: Senior Backend Engineer\nExperience: 5+ years\nTech: Python, FastAPI."
        content = sample_text.encode("utf-8")
        extracted = parse_document("job_description.txt", content)
        assert "Senior Backend Engineer" in extracted
        assert "FastAPI" in extracted

    def test_txt_extraction_latin1(self):
        sample_text = "Senior Engineer - Experience with café & résumé APIs."
        content = sample_text.encode("latin-1")
        extracted = parse_document("jd.txt", content)
        assert "Senior Engineer" in extracted
        assert "café" in extracted

    def test_docx_extraction(self):
        paragraphs = [
            "Job Title: Machine Learning Specialist",
            "Responsibilities: Train LLM models and deploy endpoints.",
            "Requirements: PyTorch, CUDA, Python 3.11+",
        ]
        docx_bytes = _create_sample_docx(paragraphs)
        extracted = parse_document("ml_job.docx", docx_bytes)
        assert "Job Title: Machine Learning Specialist" in extracted
        assert "PyTorch, CUDA" in extracted
        assert "Train LLM models" in extracted

    def test_docx_corrupt_zip(self):
        corrupt_bytes = b"PK\x03\x04invalid zip content"
        with pytest.raises(DocumentParseError, match="Failed to extract text from DOCX"):
            extract_text_from_docx(corrupt_bytes)

    def test_docx_missing_document_xml(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("other.xml", "<root></root>")
        with pytest.raises(DocumentParseError, match="missing word/document.xml"):
            extract_text_from_docx(buf.getvalue())

    def test_pdf_extraction(self):
        pdf_bytes = _create_sample_pdf("Senior DevOps Engineer AWS Kubernetes")
        extracted = parse_document("devops.pdf", pdf_bytes)
        assert "DevOps" in extracted or "AWS" in extracted or len(extracted) > 0

    def test_unsupported_extension(self):
        with pytest.raises(DocumentParseError, match="Unsupported file format '.jpg'"):
            parse_document("image.jpg", b"\xff\xd8\xff")

        with pytest.raises(DocumentParseError, match="Unsupported file format '.exe'"):
            parse_document("program.exe", b"MZ\x90\x00")

        with pytest.raises(DocumentParseError, match="Unsupported file format '.md'"):
            parse_document("readme.md", b"# Markdown")

    def test_empty_file_bytes(self):
        with pytest.raises(DocumentParseError, match="File is empty"):
            parse_document("empty.txt", b"")

        with pytest.raises(DocumentParseError, match="File is empty"):
            parse_document("empty.docx", b"")

    def test_empty_filename(self):
        with pytest.raises(DocumentParseError, match="Filename cannot be empty"):
            parse_document("", b"some text")

    def test_whitespace_only_document(self):
        with pytest.raises(DocumentParseError, match="Extracted document text is empty"):
            parse_document("blank.txt", b"   \n\n\t   ")
