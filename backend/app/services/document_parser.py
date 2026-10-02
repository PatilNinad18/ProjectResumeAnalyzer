"""
Document parser service for extracting text from .txt, .pdf, and .docx files.

This service is standalone and does NOT import web frameworks (e.g. FastAPI).
It raises DocumentParseError on parsing failures or unsupported formats so that
calling layers (API routes, CLI tools, workers) can handle errors cleanly.
"""
from __future__ import annotations

import io
import os
import zipfile
import xml.etree.ElementTree as ET
from typing import Set

SUPPORTED_EXTENSIONS: Set[str] = {".txt", ".pdf", ".docx"}


class DocumentParseError(Exception):
    """Raised when document parsing fails or the format is unsupported/empty."""
    pass


def extract_text_from_txt(content: bytes) -> str:
    """Extract plain text from raw bytes attempting UTF-8 and Latin-1 fallbacks."""
    for encoding in ("utf-8", "utf-8-sig", "latin-1", "cp1252"):
        try:
            return content.decode(encoding)
        except (UnicodeDecodeError, ValueError):
            continue
    raise DocumentParseError("Unable to decode text file with standard encodings.")


def extract_text_from_pdf(content: bytes) -> str:
    """Extract text from PDF bytes using pypdf."""
    try:
        import pypdf
        reader = pypdf.PdfReader(io.BytesIO(content))
        pages_text = []
        for idx, page in enumerate(reader.pages):
            page_str = page.extract_text() or ""
            if page_str.strip():
                pages_text.append(page_str.strip())
        return "\n\n".join(pages_text)
    except Exception as e:
        raise DocumentParseError(f"Failed to extract text from PDF: {e}") from e


def extract_text_from_docx(content: bytes) -> str:
    """
    Extract text from DOCX bytes using pure Python standard library zipfile + XML.
    Parses word/document.xml without requiring heavy external dependencies.
    """
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as docx_zip:
            if "word/document.xml" not in docx_zip.namelist():
                raise DocumentParseError("Invalid DOCX file: missing word/document.xml")
            xml_content = docx_zip.read("word/document.xml")
        
        tree = ET.fromstring(xml_content)
        # Word XML namespaces
        ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
        
        paragraphs = []
        for p in tree.iterfind(".//w:p", ns):
            texts = [node.text for node in p.iterfind(".//w:t", ns) if node.text]
            p_text = "".join(texts).strip()
            if p_text:
                paragraphs.append(p_text)
                
        return "\n\n".join(paragraphs)
    except Exception as e:
        if isinstance(e, DocumentParseError):
            raise
        raise DocumentParseError(f"Failed to extract text from DOCX: {e}") from e


def parse_document(filename: str, content: bytes) -> str:
    """
    Unified entry point for document extraction.
    
    Supports: .txt, .pdf, .docx
    Returns extracted plain text string.
    Raises DocumentParseError if unsupported, corrupt, or empty.
    """
    if not filename:
        raise DocumentParseError("Filename cannot be empty.")
    
    _, ext = os.path.splitext(filename.lower())
    if ext not in SUPPORTED_EXTENSIONS:
        raise DocumentParseError(
            f"Unsupported file format '{ext or 'unknown'}'. Supported formats: .txt, .pdf, .docx"
        )
    
    if not content or len(content) == 0:
        raise DocumentParseError("File is empty (0 bytes).")
    
    if ext == ".txt":
        text = extract_text_from_txt(content)
    elif ext == ".pdf":
        text = extract_text_from_pdf(content)
    elif ext == ".docx":
        text = extract_text_from_docx(content)
    else:
        raise DocumentParseError(f"Unhandled extension '{ext}'")
    
    cleaned_text = text.strip()
    if not cleaned_text:
        raise DocumentParseError("Extracted document text is empty or unreadable.")
    
    return cleaned_text
