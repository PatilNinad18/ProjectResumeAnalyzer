"""Deterministic assessment of resume evidence against individual JD criteria."""
from __future__ import annotations

import re
from datetime import date
from functools import lru_cache
from typing import Any

from app.services.resume.profiler import _SECTION_HEADERS, _SKILL_KEYWORDS, _total_years_from_ranges


_ALIASES = {
    "aws": ("aws", "amazon web services"),
    "postgresql": ("postgresql", "postgres"),
    "kubernetes": ("kubernetes", "k8s"),
    "next.js": ("next.js", "nextjs", "next js"),
    "node.js": ("node.js", "nodejs", "node js"),
    "ruby on rails": ("ruby on rails", "rails"),
    "go": ("Go", "golang"),
    "r": ("R",),
    "c": ("C",),
    "microservices": ("microservices", "microservice"),
    "computer science": ("computer science",),
    "information technology": ("information technology",),
    "data science": ("data science",),
    "react": ("react", "react.js", "reactjs"),
}
_ALIAS_LOOKUP = {alias.lower(): key for key, aliases in _ALIASES.items() for alias in aliases}
_OTHER_TOOLS = (
    "supabase", "sentry", "vercel", "tailwind", "shadcn", "claude code",
    "sql", "apis?", "distributed systems?", r"\.net",
)
_TECHNOLOGIES = re.compile(
    r"(?<![\w+#])(?:"
    + "|".join(sorted(
        set(_SKILL_KEYWORDS) | set(_OTHER_TOOLS) | {re.escape(name) for name in _ALIAS_LOOKUP},
        key=lambda name: (-len(name), name),
    ))
    + r")(?![\w+#])",
    re.IGNORECASE,
)
_WORD = re.compile(r"[^\W_]+(?:[.-][^\W_]+)*[+#]*", re.UNICODE)
_STOP = frozenset("""
    a an all and any are around as at be been both by can candidate candidates each element elements
    demonstrate demonstrated for from good has have in including is item items each least listed
    minimum must of on one or our preferred proficiency proficient relevant required requirement
    requirements required related should similar skills skill solid strong such technical the their
    this to use using with year years experience knowledge understanding familiarity ability hands-on
    practical proven equivalent qualifications qualification plus someone who will work working
""".split())
_APPLIED = re.compile(
    r"\b(?:architected|automated|built|configured|created|deployed|designed|developed|"
    r"delivered|implemented|improved|integrated|led|maintained|managed|migrated|"
    r"monitored|operated|optimized|owned|performed|processed|reconciled|reduced|"
    r"refactored|shipped|tested|trained|used|worked|wrote)\b",
    re.IGNORECASE,
)
_CAPABILITY_ACTIONS = {
    "deployment": r"deploy(?:ment|ed|ing|s)?|roll(?:ed|ing)? out|release[ds]?",
    "design": r"design(?:ed|ing|s)?|architect(?:ed|ing|ure)?",
    "development": r"develop(?:ment|ed|ing|s)?|built|wrote|implemented|architected",
    "operations": r"operat(?:ions?|ed|ing|e)|managed|maintained|monitored",
    "automation": r"automat(?:ion|ed|ing|e)",
    "testing": r"test(?:s|ing|ed)?",
}
_ACTION_PATTERNS = {name: re.compile(rf"\b(?:{words})\b", re.I) for name, words in _CAPABILITY_ACTIONS.items()}
_NEGATED = re.compile(
    r"\b(?:no (?:prior )?(?:experience|knowledge)|never (?:used|worked)|"
    r"(?:did|have|has) not (?:used?|work|worked|complete)|not (?:used|familiar with)|unfamiliar with)\b",
    re.IGNORECASE,
)
_LEARNING = re.compile(r"\b(?:currently learning|currently studying|in progress|expected graduation|pursuing|working toward)\b", re.I)
_PRODUCTION_CONTEXT = re.compile(r"\b(?:production|live service|live application|deployed|shipped|customers?|end users?)\b", re.I)
_YEARS = re.compile(r"\b(\d+(?:\.\d+)?)(?:\+|\s*(?:[-–—]|to)\s*\d+(?:\.\d+)?)?\s+years?\b", re.I)
_DEGREES = {
    "bachelor": re.compile(r"\b(?:(?i:bachelor|b\.?\s?(?:tech|sc|ca))|B\.?\s?[SE])\b"),
    "master": re.compile(r"\b(?:(?i:master|m\.?\s?(?:tech|sc|ca|ba))|M\.?\s?[SE])\b"),
    "doctorate": re.compile(r"\b(?:doctorate|ph\.?\s?d)\b", re.I),
    "associate": re.compile(r"\bassociate(?:'s)?\s+degree\b", re.I),
}
_CERTIFICATION = re.compile(r"\b(?:certified|certifications?|credentials?)\b", re.I)
_PASSAGE_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z])|;\s+")
_BULLET_START = re.compile(r"^(?:[-*•▪]|\d+[.)])\s*")


def _canonical_term(term: str) -> str:
    key = term.lower()
    if key == "apis":
        return "api"
    if key == "distributed system":
        return "distributed systems"
    return _ALIAS_LOOKUP.get(key, key)


def _generic_terms(text: str) -> list[str]:
    return list(dict.fromkeys(
        word.lower() for word in _WORD.findall(text)
        if len(word) > 2 and not word[0].isdigit() and word.lower() not in _STOP
    ))


@lru_cache(maxsize=512)
def _term_pattern(term: str) -> re.Pattern:
    if term in _ACTION_PATTERNS:
        return _ACTION_PATTERNS[term]
    if term in {"r", "c"}:
        return re.compile(rf"(?<![\w+#]){term.upper()}(?![\w+#])")
    if term == "go":
        return re.compile(r"(?<![\w+#])(?:Go|(?i:golang))(?![\w+#])")
    aliases = _ALIASES.get(term, (term,))
    alternatives = "|".join(re.escape(alias) for alias in aliases)
    suffix = r"s?" if term.isalpha() and len(term) > 2 and not term.endswith("s") else ""
    return re.compile(rf"(?<![\w+#])(?:{alternatives}){suffix}(?![\w+#])", re.I)


def _criterion_groups(requirement: str) -> list[set[str]]:
    matches = [
        match for match in _TECHNOLOGIES.finditer(requirement)
        if match.group() not in {"c", "r", "go"} or requirement.strip() == match.group()
    ]
    if not matches:
        return [{term} for term in _generic_terms(requirement)]
    groups: list[set[str]] = []
    previous_end = 0
    for match in matches:
        term = _canonical_term(match.group())
        separator = requirement[previous_end:match.start()]
        if groups and re.fullmatch(r"\s*(?:/|,?\s*or)\s*", separator, re.I):
            groups[-1].add(term)
        elif not any(term in group for group in groups):
            groups.append({term})
        previous_end = match.end()
    return groups


def is_assessable(requirement: str) -> bool:
    """A criterion needs a credential or at least one specific assessment term."""
    return bool(
        _criterion_groups(_CERTIFICATION.sub("", requirement))
        or any(p.search(requirement) for p in _DEGREES.values())
    )


class ResumeEvidence:
    def __init__(self, resume_text: str, profile: dict[str, Any]):
        self.source = " ".join(resume_text.split())
        self.passages = self._passages(resume_text)
        self.work_history = profile.get("work_history") or []

    @staticmethod
    def _passages(text: str) -> list[tuple[str, str]]:
        blocks: list[tuple[str, str]] = []
        section = ""
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line:
                blocks.append((section, ""))
                continue
            heading, _, rest = line.partition(":")
            for name, pattern in _SECTION_HEADERS.items():
                if pattern.fullmatch(heading.strip()):
                    section = name
                    blocks.append((section, rest.strip()))
                    break
            else:
                # A PDF bullet can wrap mid-sentence without a second marker.
                previous = blocks[-1][1] if blocks else ""
                if (
                    previous and previous[-1] not in ".!?;"
                    and not _BULLET_START.match(line)
                    and (line[0].islower() or raw_line.startswith((" ", "\t")))
                ):
                    blocks[-1] = (section, previous + "\n" + line)
                else:
                    blocks.append((section, line))
        return [
            (section, passage.strip())
            for section, block in blocks
            for passage in _PASSAGE_SPLIT.split(block)
            if passage.strip()
        ]

    def checked_quotes(self, passages: list[str | None]) -> list[str]:
        """Keep the original excerpts whose whitespace-normalized text occurs in the resume."""
        return list(dict.fromkeys(
            quote for quote in passages if quote and quote.strip() and " ".join(quote.split()) in self.source
        ))

    @staticmethod
    def _hits(groups: list[set[str]], passage: str) -> set[int]:
        normalized = " ".join(passage.split())
        return {i for i, group in enumerate(groups) if any(_term_pattern(term).search(normalized) for term in group)}

    def _relevant_passages(
        self, groups: list[set[str]], passages: list[tuple[str, str]], capabilities: list[re.Pattern],
    ):
        for section, passage in passages:
            hits = self._hits(groups, passage)
            if hits and not _NEGATED.search(passage) and self.checked_quotes([passage]):
                activity = _APPLIED.search(passage)
                normalized = " ".join(passage.split())
                applied = (
                    section != "skills"
                    and activity is not None
                    and not _LEARNING.search(passage)
                    and all(pattern.search(normalized) for pattern in capabilities)
                    and (activity.group().lower() not in {"used", "worked"} or len(_WORD.findall(passage)) >= 4)
                )
                yield passage, hits, bool(applied)

    def _dated_evidence(
        self, groups: list[set[str]], required_groups: int, capabilities: list[re.Pattern],
    ) -> tuple[float, list[str]]:
        ranges, quotes = [], []
        for role in self.work_history:
            dates = self.checked_quotes([role.get("date_text")])
            if not dates or not role.get("start_date") or not role.get("end_date"):
                continue
            passages = self._passages(role.get("description") or "")
            applied = [(quote, hits) for quote, hits, strong in self._relevant_passages(groups, passages, capabilities) if strong]
            if len(set().union(*(hits for _, hits in applied))) < required_groups:
                continue
            try:
                start, end = date.fromisoformat(role["start_date"]), date.fromisoformat(role["end_date"])
            except (ValueError, TypeError):
                continue
            if start < end:
                ranges.append((start, end))
                quotes.extend([*dates, *(quote for quote, _ in applied)])
        return _total_years_from_ranges(ranges), self.checked_quotes(quotes)

    def _degree(self, requirement: str, degree: re.Pattern, match: re.Match) -> tuple[str, list[str], str]:
        field = re.search(r"\bin\s+(.+)", requirement[match.end():], re.I)
        field_text = re.split(r"\bor (?:a )?related (?:field|discipline)\b", field.group(1), flags=re.I)[0] if field else ""
        fields = [_criterion_groups(part) for part in re.split(r",|\bor\b", field_text)]
        fields = [part for part in fields if part]
        partial = []
        for _, passage in self.passages:
            if not degree.search(passage) or _NEGATED.search(passage) or not self.checked_quotes([passage]):
                continue
            if (not fields or any(len(self._hits(part, passage)) == len(part) for part in fields)) and not _LEARNING.search(passage):
                return "MET", [passage], "The resume lists the requested degree and field."
            partial.append(passage)
        if partial:
            return "PARTIALLY_MET", partial[:2], "The degree level is listed. Confirm the field or completion."
        return "NOT_EVIDENCED", [], "The requested degree level is absent from the extracted resume text."

    def assess(self, requirement: str, guidance: list[str]) -> tuple[str, list[str], str]:
        for degree in _DEGREES.values():
            if match := degree.search(requirement):
                return self._degree(requirement, degree, match)

        credential = bool(_CERTIFICATION.search(requirement))
        subject = _CERTIFICATION.sub("", requirement) if credential else requirement
        groups = _criterion_groups(subject)
        if credential:
            # A provider alone cannot establish a named certification.
            groups = [{term} for term in _generic_terms(subject)]
        capabilities = [_ACTION_PATTERNS[term] for term in _generic_terms(subject) if term in _ACTION_PATTERNS]
        scope = re.search(r"\b(?:for|within|in)\s+([^,.;]+)", subject, re.I)
        if scope and _TECHNOLOGIES.search(subject[:scope.start()]):
            # A stated application area needs evidence alongside the named tool.
            capabilities.extend(_term_pattern(term) for term in _generic_terms(scope.group(1)))
        required_groups = len(groups)
        for rule in guidance:
            option = rule.partition(":")[0].strip().lower()
            if option == "all listed elements required":
                groups = [{term} for term in sorted(set().union(*groups))]
                required_groups = len(groups)
            elif option == "any one element qualifies":
                required_groups = 1
            elif option == "at least two required":
                groups = [{term} for term in sorted(set().union(*groups))]
                required_groups = 2
            elif option == "hands-on production depth":
                capabilities.append(_PRODUCTION_CONTEXT)

        matches = list(self._relevant_passages(groups, self.passages, capabilities))
        if not matches:
            return "NOT_EVIDENCED", [], "The extracted resume text contains no specific evidence for this criterion."

        if minimum := _YEARS.search(requirement):
            years, quotes = self._dated_evidence(groups, required_groups, capabilities)
            if quotes and years >= float(minimum.group(1)):
                return "MET", quotes, f"Dated roles evidence {years:.1f} years after counting overlapping dates once."
            return "PARTIALLY_MET", quotes or [quote for quote, _, _ in matches[:2]], (
                f"Dated roles evidence {years:.1f} years. Confirm the required duration and scope."
            )

        # Credential titles can prove the criterion without a work activity. A
        # generic skill mention only gives partial credit for a named credential.
        if credential:
            for quote, hits, _ in matches:
                if _CERTIFICATION.search(quote) and len(hits) >= required_groups and not _LEARNING.search(quote):
                    return "MET", [quote], "The resume lists the requested credential."
            return "PARTIALLY_MET", [matches[0][0]], "The subject is mentioned. Confirm the exact credential and its status."

        demonstrated = set()
        quotes = []
        for quote, hits, applied in matches:
            if applied and hits - demonstrated:
                demonstrated.update(hits)
                quotes.append(quote)
        if len(demonstrated) >= required_groups:
            return "MET", quotes, "The cited work, coursework, or project describes applying the required capability."
        if not quotes:
            quotes = [quote for quote, _, _ in matches[:2]]
        return "PARTIALLY_MET", quotes, "The resume mentions relevant skills or activity. Confirm the remaining scope or depth."
