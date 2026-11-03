"""
Ollama-powered conversational ambiguity discovery service.

Discovers genuine role trade-offs, screening dilemmas, and missing critical metadata
from raw Job Description text in Claude's style:
- Punchy 2-3 word topic tabs
- Conversational questions directly citing the JD tension
- 3-4 structured options with labels and descriptions + 'Type something'
- Evidence quotes validated against original JD text
- Bounded by a configurable timeout (default 12s) with zero-cost fallback
"""
from __future__ import annotations

import json
import logging
import os
import re
import socket
import urllib.request
import urllib.error
from typing import Any, Dict, List, Optional, Tuple

from app.schemas.master_context import QuestionCategory
from app.services.deterministic.parameter_extractor import (
    detect_team_size_value,
    detect_salary_range_value,
)

logger = logging.getLogger("jd_agent.ollama_ambiguity_service")

# Configurable timeout: defaults to 12.0 seconds
OLLAMA_AMBIGUITY_TIMEOUT_SECONDS = float(os.getenv("OLLAMA_AMBIGUITY_TIMEOUT_SECONDS", "12.0"))
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
OLLAMA_MODEL = os.getenv("LLM_MODEL", "qwen2.5:1.5b")


def _is_ollama_port_open(host: str = "127.0.0.1", port: int = 11434, timeout: float = 0.4) -> bool:
    """Fast socket probe to avoid hanging when Ollama is not listening."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except (OSError, socket.timeout):
        return False


def _normalize_text(text: str) -> str:
    """Normalize whitespace and punctuation for evidence verification."""
    return re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()


def validate_llm_ambiguity(item: Dict[str, Any], raw_jd_text: str) -> bool:
    """
    Validate an LLM-proposed ambiguity candidate against the JD evidence.

    Rules:
    1. Topic and question must be non-empty strings.
    2. Must provide at least 2 structured options with labels and descriptions.
    3. Salary & Team-Size validation:
       If field_target or topic is about team size or salary, verify that the JD
       genuinely lacks those values. If the JD already has an explicit value, REJECT.
    4. Technical ambiguities:
       Must provide an exact evidence_quote from the JD. If the quote is missing,
       too short, or cannot be matched in the raw JD text, REJECT.
    """
    if not isinstance(item, dict):
        return False

    topic = str(item.get("topic") or "").strip()
    question = str(item.get("question") or "").strip()
    field_target = str(item.get("field_target") or "").strip()
    quote = str(item.get("evidence_quote") or "").strip()
    options = item.get("options") or []

    if not topic or not question or len(question) < 15:
        return False

    # Options check
    if not isinstance(options, list) or len(options) < 2:
        return False
    for opt in options:
        if not isinstance(opt, dict) or not str(opt.get("label") or "").strip():
            return False

    # Salary & Team-size value check: do not ask if already explicitly provided
    is_team_size = (
        "team" in field_target.lower()
        or "team_size" in field_target.lower()
        or "team size" in topic.lower()
    )
    if is_team_size:
        explicit_team = detect_team_size_value(raw_jd_text)
        if explicit_team is not None:
            logger.info("Rejecting LLM team-size question: JD already specifies '%s'", explicit_team)
            return False
        return True

    is_salary = (
        "salary" in field_target.lower()
        or "compensation" in field_target.lower()
        or "salary" in topic.lower()
        or "compensation" in topic.lower()
    )
    if is_salary:
        explicit_salary = detect_salary_range_value(raw_jd_text)
        if explicit_salary is not None:
            logger.info("Rejecting LLM salary question: JD already specifies '%s'", explicit_salary)
            return False
        return True

    # Technical ambiguity: Evidence quote validation
    if not quote or quote.upper() == "ABSENT_FROM_JD":
        # Technical questions cannot claim absent from JD
        return False

    norm_quote = _normalize_text(quote)
    norm_jd = _normalize_text(raw_jd_text)
    if len(norm_quote) < 8 or norm_quote not in norm_jd:
        # Try matching a key 4-word snippet
        words = norm_quote.split()
        if len(words) >= 4:
            snippet = " ".join(words[:5])
            if snippet in norm_jd:
                return True
        logger.info("Rejecting LLM ambiguity: evidence quote '%s' not found in raw JD", quote)
        return False

    return True


class OllamaAmbiguityService:
    """Service discovering conversational ambiguities via local Ollama."""

    def __init__(self, base_url: Optional[str] = None, model: Optional[str] = None):
        self.base_url = (base_url or OLLAMA_BASE_URL).rstrip("/")
        self.model = model or OLLAMA_MODEL

    def discover_ambiguities(
        self,
        raw_jd_text: str,
        role_title: str,
        timeout: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        """
        Query Ollama with a Claude-inspired persona to discover 3-4 genuine
        ambiguities and screening dilemmas with structured options.

        Returns:
            List of validated ambiguity candidate dicts, or [] on timeout/failure.
        """
        if not raw_jd_text or not raw_jd_text.strip():
            return []

        # In unit tests, avoid calling live LLM so test suites remain fast and deterministic
        if os.getenv("TESTING") or os.getenv("PYTEST_CURRENT_TEST"):
            return []

        effective_timeout = timeout if timeout is not None else OLLAMA_AMBIGUITY_TIMEOUT_SECONDS

        # Fast socket probe: don't attempt request if Ollama is down
        host = "127.0.0.1"
        port = 11434
        if "://" in self.base_url:
            host_part = self.base_url.split("://", 1)[1]
            if ":" in host_part:
                host, port_str = host_part.split(":", 1)
                port = int(port_str.split("/")[0])
            else:
                host = host_part.split("/")[0]

        if not _is_ollama_port_open(host, port, timeout=0.5):
            logger.info("Ollama port %s:%d not reachable; using deterministic baseline", host, port)
            return []

        system_prompt = (
            "You are an expert Principal Technical Recruiter and Hiring Manager. "
            "Analyze the following Job Description to identify 3 to 4 genuine ambiguities, "
            "role trade-offs, and screening dilemmas before interviewing candidates.\n\n"
            "CRITICAL RULES:\n"
            "1. Every technical ambiguity MUST include an exact 'evidence_quote' copied verbatim from the Job Description.\n"
            "2. If Team Size or Salary/Compensation are absent from the JD, include them as conversational clarification questions (evidence_quote='ABSENT_FROM_JD'). "
            "If they ARE already stated in the JD, DO NOT ask about them.\n"
            "3. Return ONLY a valid JSON object matching this schema:\n"
            "{\n"
            '  "ambiguities": [\n'
            "    {\n"
            '      "topic": "2-3 word punchy tab label (e.g. Framework strictness, Hands-on %, Customer, Team size, Salary band)",\n'
            '      "question": "Conversational question referencing the specific JD dilemma",\n'
            '      "evidence_quote": "Verbatim quote from the JD supporting this dilemma",\n'
            '      "field_target": "Target schema path (e.g. requirements.framework_strictness, job_context.team_size, job_context.salary_range, role_overview.travel_model)",\n'
            '      "options": [\n'
            '        {"label": "...", "description": "..."},\n'
            '        {"label": "...", "description": "..."},\n'
            '        {"label": "Type something", "description": "Provide custom recruiter instructions."}\n'
            "      ]\n"
            "    }\n"
            "  ]\n"
            "}"
        )

        user_prompt = f"Job Title: {role_title}\n\nJob Description:\n{raw_jd_text.strip()}\n\nGenerate ambiguities now."

        endpoint = f"{self.base_url}/api/generate"
        payload = {
            "model": self.model,
            "system": system_prompt,
            "prompt": user_prompt,
            "format": "json",
            "stream": False,
            "options": {
                "temperature": 0.25,
                "num_predict": 500,
            },
        }

        try:
            req = urllib.request.Request(
                endpoint,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=effective_timeout) as resp:
                resp_data = json.loads(resp.read().decode("utf-8"))
                raw_response = resp_data.get("response", "")
                parsed = json.loads(raw_response)
                raw_items = parsed.get("ambiguities") or []
                if not isinstance(raw_items, list):
                    return []

                # Validate each item against evidence and absence rules
                validated = [
                    item for item in raw_items
                    if validate_llm_ambiguity(item, raw_jd_text)
                ]
                logger.info(
                    "Ollama generated %d ambiguities (%d passed evidence validation) in %.1fs",
                    len(raw_items),
                    len(validated),
                    effective_timeout,
                )
                return validated
        except (urllib.error.URLError, TimeoutError, socket.timeout) as exc:
            logger.warning("Ollama ambiguity generation timed out or failed (%s); using deterministic baseline", exc)
            return []
        except Exception as exc:
            logger.warning("Ollama ambiguity discovery error (%s); falling back cleanly", exc)
            return []


# Singleton
_INSTANCE: Optional[OllamaAmbiguityService] = None


def get_ollama_ambiguity_service() -> OllamaAmbiguityService:
    global _INSTANCE
    if _INSTANCE is None:
        _INSTANCE = OllamaAmbiguityService()
    return _INSTANCE
