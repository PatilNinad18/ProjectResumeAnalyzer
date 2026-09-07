"""
Model-agnostic LLM abstraction.

LLMService -> ProviderAdapter -> concrete provider (Anthropic, Gemini, etc.)

The rest of the app (the Agent) only talks to LLMService, so swapping or
adding providers never touches business logic. Every call records
token usage / latency / cost estimate / retries for cost tracking &
CloudWatch-style monitoring, and every request/response is printed to the
console so you can see exactly what was sent to the model and what came
back.

IMPORTANT: configuration (LLM_PROVIDER, LLM_MODEL, GEMINI_API_KEY,
ANTHROPIC_API_KEY, ...) is read from app.config.get_settings(), which is
what actually parses your .env file. Plain os.environ.get() does NOT see
.env values unless they're also set as real OS environment variables --
using it here was the bug that silently fell back to the mock provider.
"""
from __future__ import annotations

import abc
import json
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional

from app.config import get_settings


@dataclass
class LLMUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: float = 0.0
    retries: int = 0
    estimated_cost_usd: float = 0.0
    model: str = ""


@dataclass
class LLMResult:
    raw_text: str
    parsed_json: Optional[Dict[str, Any]]
    usage: LLMUsage
    prompt_version: str
    finish_reason: str = ""


class ProviderAdapter(abc.ABC):
    """Every concrete LLM provider implements this narrow interface."""

    name: str = "base"

    @abc.abstractmethod
    def complete_structured(
        self, system_prompt: str, user_prompt: str, model: str, max_tokens: int
    ) -> LLMResult:
        ...

    @abc.abstractmethod
    def complete_text(
        self, system_prompt: str, user_prompt: str, model: str, max_tokens: int
    ) -> str:
        ...


def _log_request(provider: str, model: str, system_prompt: str, user_prompt: str) -> None:
    print(f"\n[LLM REQUEST] provider={provider} model={model}")
    print(f"[LLM REQUEST] system_prompt ({len(system_prompt)} chars): {system_prompt[:500]}{'...' if len(system_prompt) > 500 else ''}")
    print(f"[LLM REQUEST] user_prompt ({len(user_prompt)} chars): {user_prompt[:1500]}{'...' if len(user_prompt) > 1500 else ''}")


def _log_response(provider: str, raw_text: str, usage: "LLMUsage", finish_reason: str = "") -> None:
    print(f"[LLM RESPONSE] provider={provider} input_tokens={usage.input_tokens} output_tokens={usage.output_tokens} latency_ms={usage.latency_ms:.0f} finish_reason={finish_reason or 'n/a'}")
    print(f"[LLM RESPONSE] raw_text ({len(raw_text)} chars): {raw_text[:1500]}{'...' if len(raw_text) > 1500 else ''}\n")
    if finish_reason and finish_reason not in ("STOP", "stop", ""):
        print(f"[LLM WARNING] provider={provider} finished with reason={finish_reason} -- response may be truncated/incomplete.")


def _dump_full_response_for_debug(provider: str, raw_text: str) -> Optional[str]:
    """
    Persist the FULL raw response to disk when JSON parsing fails, since the
    console log above only prints the first 1500 chars. Best-effort only --
    never let a debug-dump failure mask the real error.
    """
    import os

    try:
        debug_dir = os.path.join(os.getcwd(), "storage_data", "debug_llm_failures")
        os.makedirs(debug_dir, exist_ok=True)
        path = os.path.join(debug_dir, f"{provider}_{int(time.time() * 1000)}.txt")
        with open(path, "w", encoding="utf-8") as f:
            f.write(raw_text)
        print(f"[LLM DEBUG] full raw response ({len(raw_text)} chars) written to {path}")
        return path
    except Exception as exc:  # noqa: BLE001
        print(f"[LLM DEBUG] could not write debug dump: {exc}")
        return None


class AnthropicAdapter(ProviderAdapter):
    """
    Requires ANTHROPIC_API_KEY (from your .env, via Settings). In
    production this can instead be injected via AWS Secrets Manager / env
    injection -- either way, it flows through Settings.
    Import is lazy so the package is optional for local/mock development.
    """

    name = "anthropic"

    # Rough public per-token pricing used ONLY for cost estimation/telemetry.
    _PRICE_PER_1K_INPUT = 0.003
    _PRICE_PER_1K_OUTPUT = 0.015

    def complete_structured(
        self, system_prompt: str, user_prompt: str, model: str, max_tokens: int
    ) -> LLMResult:
        try:
            import anthropic  # type: ignore
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "anthropic package not installed; `pip install anthropic` "
                "or use the mock provider for local dev."
            ) from exc

        settings = get_settings()
        api_key = settings.anthropic_api_key
        if not api_key:
            raise RuntimeError(
                "Missing ANTHROPIC_API_KEY. Paste it into your local .env "
                "(LLM_PROVIDER=anthropic), or inject via AWS Secrets Manager "
                "in production."
            )

        _log_request(self.name, model, system_prompt, user_prompt)
        client = anthropic.Anthropic(api_key=api_key)
        start = time.perf_counter()
        response = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
        latency_ms = (time.perf_counter() - start) * 1000

        text = "".join(block.text for block in response.content if getattr(block, "type", "") == "text")
        finish_reason = getattr(response, "stop_reason", "") or ""

        usage = LLMUsage(
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            latency_ms=latency_ms,
            model=model,
            estimated_cost_usd=(
                response.usage.input_tokens / 1000 * self._PRICE_PER_1K_INPUT
                + response.usage.output_tokens / 1000 * self._PRICE_PER_1K_OUTPUT
            ),
        )
        _log_response(self.name, text, usage, finish_reason)

        parsed = _safe_json_extract(text)
        if parsed is None:
            _dump_full_response_for_debug(self.name, text)
            raise ValueError(f"provider=anthropic returned unparseable or truncated JSON (finish_reason={finish_reason}).")

        return LLMResult(raw_text=text, parsed_json=parsed, usage=usage, prompt_version="", finish_reason=finish_reason)


    def complete_text(
        self, system_prompt: str, user_prompt: str, model: str, max_tokens: int
    ) -> str:
        try:
            import anthropic  # type: ignore
        except ImportError as exc:
            raise RuntimeError("anthropic package not installed") from exc

        settings = get_settings()
        api_key = settings.anthropic_api_key
        if not api_key:
            raise RuntimeError("Missing ANTHROPIC_API_KEY")

        _log_request(self.name, model, system_prompt, user_prompt)
        client = anthropic.Anthropic(api_key=api_key)
        start = time.perf_counter()
        response = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
        latency_ms = (time.perf_counter() - start) * 1000
        text = "".join(block.text for block in response.content if getattr(block, "type", "") == "text")
        usage = LLMUsage(
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            latency_ms=latency_ms,
            model=model,
        )
        _log_response(self.name, text, usage)
        return text



class GeminiAdapter(ProviderAdapter):
    """
    Google Gemini adapter, for free-tier testing (Flash / Flash-Lite models
    currently have a no-cost quota via Google AI Studio: ai.google.dev).
    Uses the REST API directly via `requests` so no extra SDK is required.

    Set (in your .env):
        LLM_PROVIDER=gemini
        LLM_MODEL=gemini-2.5-flash          (or gemini-2.5-flash-lite)
        GEMINI_API_KEY=<from Google AI Studio>

    Note: Gemini has no separate "system" role in the same shape as
    Anthropic's Messages API; we pass it via `system_instruction` and put
    the JD content in the single user turn, keeping the same
    data-not-instructions framing as the Anthropic path.
    """

    name = "gemini"

    # Rough public per-token pricing for Flash, used only for cost
    # estimation/telemetry -- $0 while within the free-tier quota.
    _PRICE_PER_1K_INPUT = 0.0
    _PRICE_PER_1K_OUTPUT = 0.0

    def complete_structured(
        self, system_prompt: str, user_prompt: str, model: str, max_tokens: int
    ) -> LLMResult:
        try:
            import requests  # type: ignore
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("`pip install requests` to use GeminiAdapter.") from exc

        settings = get_settings()
        api_key = settings.gemini_api_key
        if not api_key or api_key.strip().lower() in ("", "paste-your-gemini-key-here"):
            raise RuntimeError(
                "Missing/placeholder GEMINI_API_KEY. Get a free key at "
                "https://aistudio.google.com/apikey and paste it into your "
                "local .env as GEMINI_API_KEY=..."
            )

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"

        def _build_payload(include_thinking_config: bool) -> Dict[str, Any]:
            generation_config: Dict[str, Any] = {
                "maxOutputTokens": max_tokens,
                "responseMimeType": "application/json",
            }
            if include_thinking_config:
                generation_config["thinkingConfig"] = {"thinkingBudget": 0}
            return {
                "system_instruction": {"parts": [{"text": system_prompt}]},
                "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
                "generationConfig": generation_config,
            }

        _log_request(self.name, model, system_prompt, user_prompt)

        # Gemini 2.5+/3.x models "think" by default, sharing maxOutputTokens
        # with the visible answer, which can truncate a large JSON response.
        # We try to disable thinking to free up the full budget -- but not
        # every model/API version accepts `thinkingConfig` (some reject it
        # with a 400 INVALID_ARGUMENT), so if that happens we transparently
        # retry the SAME call once without it rather than failing outright.
        attempt_with_thinking_config = not model.startswith("gemini-1.")
        start = time.perf_counter()
        response = requests.post(url, json=_build_payload(attempt_with_thinking_config), timeout=120)

        if response.status_code == 400 and attempt_with_thinking_config:
            print(
                f"[LLM RESPONSE] provider=gemini HTTP 400 with thinkingConfig set "
                f"(model={model} may not support it): {response.text[:500]}"
            )
            print("[LLM RETRY] provider=gemini retrying without thinkingConfig...")
            response = requests.post(url, json=_build_payload(False), timeout=120)

        latency_ms = (time.perf_counter() - start) * 1000
        if not response.ok:
            print(f"[LLM RESPONSE] provider=gemini HTTP {response.status_code}: {response.text[:1000]}")
        response.raise_for_status()
        data = response.json()

        candidates = data.get("candidates", [])
        text = "".join(
            part.get("text", "")
            for candidate in candidates
            for part in candidate.get("content", {}).get("parts", [])
        )
        finish_reason = candidates[0].get("finishReason", "") if candidates else ""

        usage_meta = data.get("usageMetadata", {})
        input_tokens = usage_meta.get("promptTokenCount", 0)
        output_tokens = usage_meta.get("candidatesTokenCount", 0)
        thoughts_tokens = usage_meta.get("thoughtsTokenCount", 0)
        if thoughts_tokens:
            print(f"[LLM RESPONSE] provider=gemini thoughts_token_count={thoughts_tokens} (should be ~0 with thinkingBudget=0)")

        usage = LLMUsage(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=latency_ms,
            model=model,
            estimated_cost_usd=(
                input_tokens / 1000 * self._PRICE_PER_1K_INPUT
                + output_tokens / 1000 * self._PRICE_PER_1K_OUTPUT
            ),
        )
        _log_response(self.name, text, usage, finish_reason)

        parsed = _safe_json_extract(text)
        if parsed is None:
            _dump_full_response_for_debug(self.name, text)
            raise ValueError(f"provider=gemini returned unparseable or truncated JSON (finish_reason={finish_reason}).")

        return LLMResult(raw_text=text, parsed_json=parsed, usage=usage, prompt_version="", finish_reason=finish_reason)


    def complete_text(
        self, system_prompt: str, user_prompt: str, model: str, max_tokens: int
    ) -> str:
        import requests  # type: ignore

        settings = get_settings()
        api_key = settings.gemini_api_key
        if not api_key or api_key.strip().lower() in ("", "paste-your-gemini-key-here"):
            raise RuntimeError("Missing GEMINI_API_KEY")

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
        payload = {
            "system_instruction": {"parts": [{"text": system_prompt}]},
            "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
            "generationConfig": {"maxOutputTokens": max_tokens},
        }

        _log_request(self.name, model, system_prompt, user_prompt)
        start = time.perf_counter()
        response = requests.post(url, json=payload, timeout=120)
        latency_ms = (time.perf_counter() - start) * 1000
        response.raise_for_status()
        data = response.json()
        candidates = data.get("candidates", [])
        text = "".join(
            part.get("text", "")
            for candidate in candidates
            for part in candidate.get("content", {}).get("parts", [])
        )
        usage_meta = data.get("usageMetadata", {})
        usage = LLMUsage(
            input_tokens=usage_meta.get("promptTokenCount", 0),
            output_tokens=usage_meta.get("candidatesTokenCount", 0),
            latency_ms=latency_ms,
            model=model,
        )
        _log_response(self.name, text, usage)
        return text



class MockAdapter(ProviderAdapter):
    """
    Deterministic offline provider used for local dev, CI and tests so the
    whole pipeline (agent -> schema -> renderer -> converter -> API) can be
    exercised without any network access or API key.

    It applies a tiny rule-based extraction over the JD text. This is NOT a
    substitute for the real model -- it only unblocks development/testing
    of the surrounding system. If you're seeing "mock-extractor-v1" in your
    output's metadata and expected Gemini/Anthropic, check LLM_PROVIDER in
    your .env.
    """

    name = "mock"

    def complete_structured(
        self, system_prompt: str, user_prompt: str, model: str, max_tokens: int
    ) -> LLMResult:
        from app.services.mock_extractor import mock_extract_canonical

        print("\n[LLM REQUEST] provider=mock (no real API call -- rule-based extraction only)")
        start = time.perf_counter()
        jd_text = _extract_jd_text(user_prompt)
        canonical_dict = mock_extract_canonical(jd_text)
        latency_ms = (time.perf_counter() - start) * 1000

        usage = LLMUsage(
            input_tokens=len(user_prompt.split()),
            output_tokens=len(json.dumps(canonical_dict).split()),
            latency_ms=latency_ms,
            model="mock-extractor-v1",
            estimated_cost_usd=0.0,
        )
        print(f"[LLM RESPONSE] provider=mock model_version=mock-extractor-v1 (rule-based, not from a real LLM)\n")
        return LLMResult(
            raw_text=json.dumps(canonical_dict, indent=2, default=str),
            parsed_json=canonical_dict,
            usage=usage,
            prompt_version="",
        )

    def complete_text(
        self, system_prompt: str, user_prompt: str, model: str, max_tokens: int
    ) -> str:
        import re

        print("\n[LLM REQUEST] provider=mock complete_text")
        question_text = user_prompt
        if "User Question:" in user_prompt:
            question_text = user_prompt.split("User Question:", 1)[1]
        lower_q = question_text.lower()

        # 1. Salary / Compensation Queries
        if any(w in lower_q for w in ["salary", "compensation", "pay", "ctc", "lpa", "inr", "usd", "money", "reward", "package"]):
            salary_match = re.search(
                r"(\d+\s*K?\s*(?:INR|USD|EUR|GBP|₹|\$)\s*/\s*(?:month|year|annum)|\d+\s*-\s*\d+\s*K?\s*(?:INR|USD|₹|\$)|(?:₹|\$)?\s*\d+\s*K?\s*(?:INR|USD)?\s*/\s*month\s*-\s*\d+\s*K?\s*(?:INR|USD)?\s*/\s*month|\d+\s*-\s*\d+\s*(?:LPA|CTC|lpa|ctc))",
                user_prompt,
                re.IGNORECASE,
            )
            if salary_match:
                return f"- **Salary Range:** {salary_match.group(0).strip()}\n- **Details:** Specified in the job requirements."

            sal_lines = [line.strip("-* ") for line in user_prompt.splitlines() if any(k in line.lower() for k in ["inr", "usd", "salary", "compensation", "lpa", "ctc", "month"])]
            if sal_lines:
                bullets = "\n".join([f"- {line}" for line in sal_lines[:4]])
                return bullets

            return "The job description does not explicitly state a salary range or compensation numbers."

        # 2. Title & Seniority / Experience Queries
        if any(w in lower_q for w in ["title", "role", "position", "seniority", "senior", "experience", "year", "level"]):
            matched_lines = [line.strip("-* ") for line in user_prompt.splitlines() if any(k in line.lower() for k in ["job title", "seniority", "role", "experience", "engineer", "lead", "manager", "years"])]
            bullets = "\n".join([f"- {line}" for line in matched_lines[:6]]) if matched_lines else "- Senior software role with experience expectations outlined in the requirements."
            return bullets

        # 3. Technical Skills & Requirements Queries
        if any(w in lower_q for w in ["skill", "tech", "python", "stack", "require", "qualification", "must", "preferred"]):
            matched_lines = [line.strip("-* ") for line in user_prompt.splitlines() if any(k in line.lower() for k in ["skill", "require", "experience", "python", "scikit", "tensorflow", "pytorch", "aws", "gcp", "azure", "docker", "must", "preferred"])]
            bullets = "\n".join([f"- {line}" for line in matched_lines[:15]]) if matched_lines else "- Core technical skills include Python, backend architecture, and cloud services."
            return bullets

        # 4. Remote / Location / Workplace Queries
        if any(w in lower_q for w in ["remote", "location", "office", "where", "hybrid", "city", "india", "place", "country"]):
            matched_lines = [line.strip("-* ") for line in user_prompt.splitlines() if any(k in line.lower() for k in ["remote", "location", "office", "hybrid", "onsite", "city", "india", "work mode"])]
            bullets = "\n".join([f"- {line}" for line in matched_lines[:4]]) if matched_lines else "- Work location and attendance policies as specified in role overview."
            return bullets

        # 5. Responsibilities Queries
        if any(w in lower_q for w in ["responsibil", "duty", "do", "task", "deliver", "build", "design", "deploy"]):
            matched_lines = [line.strip("-* ") for line in user_prompt.splitlines() if any(k in line.lower() for k in ["responsib", "duty", "deliver", "build", "lead", "manage", "design", "develop", "deploy", "optimize"])]
            bullets = "\n".join([f"- {line}" for line in matched_lines[:8]]) if matched_lines else "- Design, develop, and maintain core services and collaborate across teams."
            return bullets

        # 6. Fallback General Query Scanner
        matched_lines = [line.strip("-* ") for line in user_prompt.splitlines() if len(line.strip()) > 15 and not line.startswith("#")]
        bullets = "\n".join([f"- {line}" for line in matched_lines[:5]]) if matched_lines else "I am ready to assist with details regarding role qualifications, skills, or responsibilities."
        return bullets




def _extract_jd_text(user_prompt: str) -> str:

    marker = "<jd_content>"
    end_marker = "</jd_content>"
    if marker in user_prompt and end_marker in user_prompt:
        return user_prompt.split(marker, 1)[1].split(end_marker, 1)[0].strip()
    return user_prompt


def _repair_truncated_json(text: str) -> Optional[Dict[str, Any]]:
    import re

    start = text.find("{")
    if start == -1:
        return None
    sub = text[start:].strip()
    sub = re.sub(r',\s*"[^"]*"?\s*:?\s*"?[^"]*$', "", sub)
    sub = re.sub(r',\s*$', "", sub)

    stack = []
    in_string = False
    escaped = False
    clean_chars = []

    for ch in sub:
        if escaped:
            escaped = False
            clean_chars.append(ch)
            continue
        if ch == "\\" and in_string:
            escaped = True
            clean_chars.append(ch)
            continue
        if ch == '"':
            in_string = not in_string
            clean_chars.append(ch)
            continue
        if in_string:
            clean_chars.append(ch)
            continue

        if ch in ("{", "["):
            stack.append("}" if ch == "{" else "]")
            clean_chars.append(ch)
        elif ch in ("}", "]"):
            if stack and stack[-1] == ch:
                stack.pop()
            clean_chars.append(ch)
        else:
            clean_chars.append(ch)

    if in_string:
        clean_chars.append('"')

    while stack:
        clean_chars.append(stack.pop())

    repaired = "".join(clean_chars)
    try:
        res = json.loads(repaired, strict=False)
        if isinstance(res, dict):
            print("[LLM REPAIR SUCCESS] Successfully repaired truncated JSON response!")
            return res
    except Exception:
        pass
    return None


def _safe_json_extract(text: str) -> Optional[Dict[str, Any]]:
    """Extract a JSON object even if the model wrapped it in prose/fences."""
    text = text.strip()

    try:
        return json.loads(text, strict=False)
    except json.JSONDecodeError:
        pass

    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]

    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        candidate = text[start : end + 1]
        try:
            return json.loads(candidate, strict=False)
        except json.JSONDecodeError:
            pass

    return _repair_truncated_json(text)


class LLMService:
    """Facade used by the rest of the application."""

    def __init__(self, adapter: Optional[ProviderAdapter] = None, model: Optional[str] = None):
        settings = get_settings()
        provider_name = settings.llm_provider
        default_models = {
            "anthropic": "claude-sonnet-4-6",
            "gemini": "gemini-1.5-flash",
            "mock": "mock-extractor-v1",
        }
        adapters = {
            "anthropic": AnthropicAdapter,
            "gemini": GeminiAdapter,
            "mock": MockAdapter,
        }
        self.adapter = adapter or adapters.get(provider_name, MockAdapter)()
        self.model = model or settings.llm_model or default_models.get(provider_name, "mock-extractor-v1")
        self.max_retries = 2
        print(f"[LLM SERVICE] configured provider={provider_name} model={self.model}")

    def complete_structured(self, system_prompt: str, user_prompt: str, max_tokens: int = 16384) -> LLMResult:
        last_exc: Optional[Exception] = None
        for attempt in range(self.max_retries + 1):
            try:
                result = self.adapter.complete_structured(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    model=self.model,
                    max_tokens=max_tokens,
                )
                result.usage.retries = attempt
                return result
            except Exception as exc:  # noqa: BLE001
                print(f"[LLM ERROR] attempt {attempt + 1}/{self.max_retries + 1} failed: {exc}")
                last_exc = exc

                continue

        if not isinstance(self.adapter, MockAdapter):
            print(f"\n[LLM WARNING] {self.adapter.name.upper()} API call failed after {self.max_retries + 1} attempts ({last_exc}).")
            print("[LLM FALLBACK] Falling back to MockAdapter (offline rule-based extractor) to keep application running!\n")
            return MockAdapter().complete_structured(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                model="mock-extractor-v1",
                max_tokens=max_tokens,
            )

        raise RuntimeError(f"LLM call failed after {self.max_retries + 1} attempts: {last_exc}")

    def chat_with_jd_context(self, markdown_context: str, question: str, max_tokens: int = 2000) -> str:
        system_prompt = (
            "You are an intelligent Job Description (JD) AI Assistant.\n"
            "Answer the user's question directly, naturally, and conversationally based on the provided Job Description context.\n"
            "Rules:\n"
            "1. Answer directly and concisely.\n"
            "2. Do NOT announce context scanning/re-scanning or state process phrases like 'Based on the JD context...' or 'I scanned...'\n"
            "3. Mention the Job Description only when relevant or explicitly asked.\n"
            "4. Format responses using clean, readable markdown."
        )
        user_prompt = (
            f"Here is the converted Job Description Markdown context:\n\n"
            f"<jd_markdown>\n{markdown_context}\n</jd_markdown>\n\n"
            f"User Question: {question}"
        )
        for attempt in range(self.max_retries + 1):
            try:
                return self.adapter.complete_text(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    model=self.model,
                    max_tokens=max_tokens,
                )
            except Exception as exc:
                print(f"[LLM CHAT ERROR] attempt {attempt + 1}/{self.max_retries + 1} failed: {exc}")
                continue

        if not isinstance(self.adapter, MockAdapter):
            print(f"[LLM CHAT FALLBACK] Falling back to MockAdapter for chat response.")
            return MockAdapter().complete_text(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                model="mock-extractor-v1",
                max_tokens=max_tokens,
            )
        raise RuntimeError("Chat LLM call failed")