"""
Unit tests for Quote Verification in Resume Screening Evaluator.
Validates:
- Exact verbatim matching
- Normalized whitespace and newline tolerance
- Ellipsis and quote wrapping handling
- Rejection of fabricated quotes
- Rejection of disconnected keywords scattered across the document
- Contiguous substring requirements for short quotes (<= 3 words)
- Integration downgrade of requirements with unverified quotes
"""
import pytest
from app.services.resume.evaluator import (
    verify_quote_in_text,
    evaluate_candidate,
)

SAMPLE_RESUME_TEXT = """
Jane Doe
Senior Backend Engineer | Distributed Systems Specialist
jane.doe@example.com | (555) 123-4567 | San Francisco, CA

PROFESSIONAL SUMMARY
Results-driven software architect with 8+ years architecting fault-tolerant microservices,
optimizing high-throughput Kafka streaming pipelines, and scaling PostgreSQL clusters on AWS.

PROFESSIONAL EXPERIENCE

Senior Backend Engineer | CloudScale Inc.
Jan 2020 - Present (4 years 3 months)
- Designed and deployed event-driven event ingestion pipeline in Python 3.11 processing 45,000 events/sec with Apache Kafka.
- Optimized PostgreSQL database query execution plans, reducing p99 latency from 450ms to 28ms using multi-column indexes.
- Provisioned and managed AWS infrastructure using Terraform and Docker containers orchestrated by Kubernetes EKS.
- Mentored 4 junior engineers on distributed systems consensus protocols and clean architecture patterns.

Software Engineer | DataCore Systems
Jun 2016 - Dec 2019 (3 years 6 months)
- Developed RESTful microservices using FastAPI and Go for payment processing workflows.
- Implemented Celery distributed task queues backed by Redis for asynchronous batch settlement jobs.
- Automated CI/CD deployment pipelines using GitHub Actions, decreasing build failures by 35%.

EDUCATION
B.S. in Computer Science | University of California, Berkeley
Graduated May 2016

SKILLS
Languages: Python, Go, SQL, Bash
Technologies: Kafka, Docker, Kubernetes, AWS, PostgreSQL, Redis, FastAPI, Git
"""

def test_exact_verbatim_quote():
    quote = "Designed and deployed event-driven event ingestion pipeline in Python 3.11 processing 45,000 events/sec with Apache Kafka."
    assert verify_quote_in_text(quote, SAMPLE_RESUME_TEXT) is True

def test_quote_with_whitespace_and_newlines():
    # Minor formatting differences from PDF wrapping
    quote = "Designed and deployed event-driven\n  event ingestion pipeline in Python 3.11\n processing 45,000 events/sec"
    assert verify_quote_in_text(quote, SAMPLE_RESUME_TEXT) is True

def test_quote_with_ellipsis_and_wrapping():
    # LLM often returns quotes starting or ending with ... or in quotation marks
    quote = '“...Optimized PostgreSQL database query execution plans, reducing p99 latency from 450ms to 28ms...”'
    assert verify_quote_in_text(quote, SAMPLE_RESUME_TEXT) is True

def test_quote_with_minor_ocr_noise():
    # High sequence similarity (> 82%) with minor punctuation difference
    quote = "Optimized PostgreSQL database query execution plans reducing p99 latency from 450ms to 28ms using multi column indexes"
    assert verify_quote_in_text(quote, SAMPLE_RESUME_TEXT) is True

def test_fabricated_quote_rejected():
    # Claiming skills/accomplishments completely absent from resume
    fake_quote = "Engineered C++ machine learning inference engine for real-time autonomous driving vehicles"
    assert verify_quote_in_text(fake_quote, SAMPLE_RESUME_TEXT) is False

def test_disconnected_keywords_rejected():
    # All these words appear in the resume ("Python", "Kafka", "PostgreSQL", "payment", "Go", "Docker")
    # but never in this hallucinated combination or sequence!
    disconnected = "Engineered Go payment Docker microservices processing Kafka PostgreSQL pipeline"
    assert verify_quote_in_text(disconnected, SAMPLE_RESUME_TEXT) is False

def test_short_quote_contiguous_match():
    # Short quotes (<= 3 words) must be exact contiguous substrings
    assert verify_quote_in_text("Apache Kafka", SAMPLE_RESUME_TEXT) is True
    assert verify_quote_in_text("Celery distributed task", SAMPLE_RESUME_TEXT) is True
    assert verify_quote_in_text("Kafka Go Redis", SAMPLE_RESUME_TEXT) is False

def test_empty_or_whitespace_quote():
    assert verify_quote_in_text("", SAMPLE_RESUME_TEXT) is False
    assert verify_quote_in_text("   ", SAMPLE_RESUME_TEXT) is False
    assert verify_quote_in_text("...", SAMPLE_RESUME_TEXT) is False

def test_downgrade_unverified_quote_in_evaluation():
    """Verify that an evaluation with an unevidenced or fabricated quote is downgraded to NOT_EVIDENCED."""
    # Requirement not supported in resume
    req = "5+ years of experience with Apache Spark and Hadoop clusters"
    
    # 1. Directly verify quote check rejects hallucinated evidence
    fake_quote = "Managed Apache Spark and Hadoop clusters for big data analytics"
    assert verify_quote_in_text(fake_quote, SAMPLE_RESUME_TEXT) is False

    # 2. The production evaluator awards no credit without supporting evidence.
    grade, = evaluate_candidate(SAMPLE_RESUME_TEXT, {}, {"must_haves": [req]})["detailed_evaluations"]
    assert grade["status"] == "NOT_EVIDENCED"
    assert grade["score_weight"] == 0.0
    assert grade["quote_verified"] is not True
