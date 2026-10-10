"""
Three-tier responsibility interpretation service (Stage 4 enhanced).

Maps JD responsibilities to required capabilities with tier classification:
- PRIMARY: Core job function (clear action ownership verbs)
- SECONDARY: Supporting activities (collaborative, assisting verbs)
- SITUATIONAL: Context-dependent tasks (conditional/sporadic signals)

Three interpretation tiers:
  Tier 1 — Deterministic EKG (always active, offline, no LLM)
  Tier 2 — Optional LLM hypothesis (extension point only; no call by default)
  Tier 3 — TA/HR-confirmed interpretation (accepted only when explicitly supplied)

Confidence separation:
  entity_confidence  — EKG match quality for each matched entity
  interpretation_confidence — strength of tier assignment given the evidence

Design principles:
- Preserve original responsibility text; never invent text
- Distinguish direct EKG matches from relationship-derived expansions
- No mandatory requirement inferred from responsibility alone
- Deterministic and offline by default
- LLM extension point documented and guarded; never auto-called
- TA/HR facts kept strictly separate from JD evidence
"""
from __future__ import annotations

import logging
import re
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set

from app.schemas.master_context import (
    ClauseType,
    ConfidenceLevel,
    ResponsibilityContext,
    ResponsibilityTier,
    SourceReference,
    StructuredRequirement,
)
from app.services.ekg import get_ekg
from app.services.deterministic.source_spans import SpanBuilder, normalize_line_endings

logger = logging.getLogger("jd_agent.interpretation")


# ---------------------------------------------------------------------------
# Internal evidence types (not exported via master_context.py)
# ---------------------------------------------------------------------------

@dataclass
class EntityMatch:
    """Single EKG entity match with supporting evidence."""
    entity_id: str
    entity_name: str
    match_confidence: float       # Entity-match confidence (EKG quality)
    matched_text: str             # Exact text fragment that triggered the match
    is_graph_derived: bool = False  # True → derived via EKG relationship, not direct text match


@dataclass
class TierEvidence:
    """Evidence used for tier classification."""
    tier: ResponsibilityTier
    signals_found: List[str]      # Human-readable list of found signal terms
    interpretation_confidence: ConfidenceLevel  # Interpretation confidence (separate from entity match)
    rationale: str


@dataclass
class LLMHypothesis:
    """
    Optional model-generated interpretation hypothesis.

    Tier 2 extension point — populated only when an LLM hook is provided by
    the caller. Never auto-called; never converted to mandatory requirements.
    """
    hypothesis_text: str
    model_name: str
    is_confirmed: bool = False    # Always False until Tier 3 confirms


@dataclass
class TAConfirmedFact:
    """
    TA/HR-confirmed interpretation fact.

    Tier 3 — accepted only when explicitly supplied via clarification context.
    Kept strictly separate from JD evidence.
    """
    fact_text: str
    confirmed_by: str             # e.g. "TA/HR via clarification answer"
    source_answer: str            # The exact TA/HR answer text


@dataclass
class RichResponsibilityContext:
    """
    Internal rich interpretation output; wraps ResponsibilityContext with
    additional provenance that the current schema cannot represent.

    The .to_schema_type() method returns a schema-compatible ResponsibilityContext.
    Fields beyond the schema are held here for Intern 2 consumption.
    """
    schema_context: ResponsibilityContext
    entity_matches: List[EntityMatch] = field(default_factory=list)
    tier_evidence: Optional[TierEvidence] = None
    llm_hypothesis: Optional[LLMHypothesis] = None
    ta_confirmed_facts: List[TAConfirmedFact] = field(default_factory=list)

    def to_schema_type(self) -> ResponsibilityContext:
        """Return schema-compatible view; extra provenance lives in this wrapper."""
        return self.schema_context


# ---------------------------------------------------------------------------
# Interpreter
# ---------------------------------------------------------------------------

class ResponsibilityInterpreter:
    """
    Three-tier responsibility interpretation engine.

    Tier 1 (deterministic, always active):
        Uses EKG entity matching and reviewed graph relationships.
        Clearly distinguishes direct matches from graph-derived expansions.

    Tier 2 (optional LLM extension point):
        Accepts an optional callable `llm_hook(text: str) -> str`.
        The hook is NEVER called unless the caller explicitly supplies it.
        Output is tagged as unconfirmed hypothesis; never mandatory.

    Tier 3 (TA/HR confirmed):
        Accepts explicit clarification context dict `{responsibility_id: answer}`.
        Confirmed facts are kept separate from JD evidence.
    """

    def __init__(
        self,
        llm_hook: Optional[Callable[[str], str]] = None,
    ):
        """
        Args:
            llm_hook: Optional callable for Tier 2 LLM hypotheses.
                      Signature: (responsibility_text: str) -> hypothesis_str
                      Defaults to None → deterministic-only mode.
        """
        self.ekg = get_ekg()
        self._llm_hook: Optional[Callable[[str], str]] = llm_hook

        # Primary signals (tier classification)
        self._primary_signals = [
            'design', 'architect', 'build', 'develop', 'implement',
            'own', 'ownership', 'lead', 'drive', 'responsible for',
            'primary', 'core', 'main', 'key', 'deliver', 'create',
            'define', 'establish', 'launch', 'ship', 'deploy',
        ]
        self._secondary_signals = [
            'support', 'assist', 'contribute', 'participate',
            'collaborate', 'work with', 'help', 'maintain',
            'secondary', 'additional', 'also', 'monitor',
            'review', 'document', 'report', 'coordinate',
        ]
        self._situational_signals = [
            'may', 'might', 'could', 'occasionally', 'as needed',
            'when required', 'if needed', 'from time to time',
            'situational', 'ad hoc', 'as appropriate', 'sometimes',
            'on occasion', 'where applicable',
        ]

    # ------------------------------------------------------------------
    # Public API — preserved from Stage 1
    # ------------------------------------------------------------------

    def interpret_responsibilities(
        self,
        requirements: List[StructuredRequirement],
        jd_text: str,
        clarification_context: Optional[Dict[str, str]] = None,
    ) -> List[ResponsibilityContext]:
        """
        Interpret responsibilities and return schema-compatible contexts.

        Args:
            requirements: All extracted requirements from the JD.
            jd_text: Original JD text (unchanged; never rewritten).
            clarification_context: Optional TA/HR answers keyed by requirement_id
                                   or ambiguity_id. Accepted only when explicitly
                                   supplied; never auto-trusted.

        Returns:
            List of ResponsibilityContext objects (shared schema).
        """
        rich_contexts = self.interpret_responsibilities_rich(
            requirements, jd_text, clarification_context
        )
        return [rc.to_schema_type() for rc in rich_contexts]

    def interpret_responsibilities_rich(
        self,
        requirements: List[StructuredRequirement],
        jd_text: str,
        clarification_context: Optional[Dict[str, str]] = None,
    ) -> List[RichResponsibilityContext]:
        """
        Full interpretation returning rich internal contexts.

        Intern 2 can consume the extra provenance fields in RichResponsibilityContext
        for display, persistence, and lifecycle management.
        """
        # Normalise line endings so span offsets are consistent
        normalised_jd = normalize_line_endings(jd_text)
        span_builder = SpanBuilder(normalised_jd)

        responsibilities = [
            req for req in requirements
            if req.clause_type == ClauseType.RESPONSIBILITY
        ]

        logger.info(
            "[Interpretation] Processing %d responsibilities (Tier 1 deterministic)",
            len(responsibilities),
        )

        rich_contexts: List[RichResponsibilityContext] = []
        for resp in responsibilities:
            rc = self._interpret_single_rich(
                resp,
                requirements,
                span_builder,
                clarification_context or {},
            )
            if rc:
                rich_contexts.append(rc)

        return rich_contexts

    # ------------------------------------------------------------------
    # Tier 1 — Deterministic EKG interpretation
    # ------------------------------------------------------------------

    def _interpret_single_rich(
        self,
        responsibility: StructuredRequirement,
        all_requirements: List[StructuredRequirement],
        span_builder: SpanBuilder,
        clarification_context: Dict[str, str],
    ) -> Optional[RichResponsibilityContext]:
        """Interpret one responsibility clause across all three tiers."""

        # --- Tier 1: EKG entity matching ---
        entity_matches = self._match_entities_with_evidence(
            responsibility, span_builder
        )

        # Derive related entities via graph relationships (clearly flagged)
        graph_derived = self._derive_graph_relationships(entity_matches)

        # Classify tier from text evidence
        tier_evidence = self._classify_tier_with_evidence(responsibility)

        # Map required capabilities via entity overlap
        capabilities = self._map_to_capabilities(
            responsibility, all_requirements, entity_matches
        )

        # Assess interpretation confidence
        interp_confidence = self._assess_interpretation_confidence(
            tier_evidence, entity_matches, capabilities
        )

        # Build rationale
        rationale = self._build_rationale(
            tier_evidence, entity_matches, graph_derived, capabilities, all_requirements
        )

        # --- Tier 2: Optional LLM hypothesis ---
        llm_hyp = self._attempt_llm_hypothesis(responsibility)

        # --- Tier 3: TA/HR confirmed facts ---
        ta_facts = self._extract_ta_facts(
            responsibility, clarification_context
        )

        # Build schema-compatible context (only schema fields; no extras)
        schema_ctx = ResponsibilityContext(
            responsibility_id=responsibility.requirement_id,
            description=responsibility.text,   # preserved verbatim
            tier=tier_evidence.tier,
            required_capabilities=capabilities,
            rationale=rationale,
            source=responsibility.source,
            interpretation_confidence=interp_confidence,
        )

        return RichResponsibilityContext(
            schema_context=schema_ctx,
            entity_matches=entity_matches + graph_derived,
            tier_evidence=tier_evidence,
            llm_hypothesis=llm_hyp,
            ta_confirmed_facts=ta_facts,
        )

    def _match_entities_with_evidence(
        self,
        responsibility: StructuredRequirement,
        span_builder: SpanBuilder,
    ) -> List[EntityMatch]:
        """
        Match EKG entities and record which text fragment triggered each match.

        Entity-match confidence comes from the EKG; it is SEPARATE from
        interpretation confidence.
        """
        matches: List[EntityMatch] = []
        text = responsibility.text
        ekg_matches = self.ekg.match_entities(text)

        for entity_id, match_confidence in ekg_matches:
            entity_info = self.ekg.get_entity_info(entity_id)
            if not entity_info:
                continue

            entity_name = entity_info.get("name", entity_id)

            # Find the specific text fragment that matched
            matched_fragment = self._find_matched_fragment(
                text, entity_name, entity_info.get("aliases", [])
            )

            matches.append(EntityMatch(
                entity_id=entity_id,
                entity_name=entity_name,
                match_confidence=match_confidence,
                matched_text=matched_fragment,
                is_graph_derived=False,
            ))

        return matches

    def _find_matched_fragment(
        self,
        text: str,
        entity_name: str,
        aliases: List[str],
    ) -> str:
        """
        Find the exact text fragment that matched an entity.

        Returns entity_name as fallback if no direct match found in text.
        """
        candidates = [entity_name] + list(aliases)
        text_lower = text.lower()

        for candidate in candidates:
            if candidate.lower() in text_lower:
                # Find case-insensitive position and return original case
                idx = text_lower.find(candidate.lower())
                return text[idx: idx + len(candidate)]

        # Fallback: return entity name (match may have been fuzzy)
        return entity_name

    def _derive_graph_relationships(
        self,
        direct_matches: List[EntityMatch],
    ) -> List[EntityMatch]:
        """
        Derive additional context from EKG graph relationships.

        Uses reviewed graph edges to find related entities (e.g. a language
        entity's known domain usage). Clearly flags all derived matches with
        `is_graph_derived=True`.

        NEVER invents entities not in the reviewed graph.
        """
        derived: List[EntityMatch] = []
        direct_ids = {m.entity_id for m in direct_matches}

        for match in direct_matches:
            # Get graph neighbours via reviewed relationships
            try:
                successors = list(self.ekg.graph.successors(match.entity_id))
            except Exception:
                continue

            for neighbour_id in successors:
                if neighbour_id in direct_ids:
                    continue  # already a direct match

                entity_info = self.ekg.get_entity_info(neighbour_id)
                if not entity_info:
                    continue

                # Get edge data to understand the relationship type
                edge_data = self.ekg.graph.get_edge_data(
                    match.entity_id, neighbour_id, default={}
                )
                rel_type = edge_data.get("relationship", "relates_to")

                # Only propagate well-understood, reviewed relationship types
                # Avoid inventing domain membership from tenuous connections
                allowed_rels = {
                    "used_in_domain", "requires_skill", "used_with",
                    "part_of", "relates_to",
                }
                if rel_type not in allowed_rels:
                    continue

                derived.append(EntityMatch(
                    entity_id=neighbour_id,
                    entity_name=entity_info.get("name", neighbour_id),
                    match_confidence=0.5,   # Reduced confidence for derived
                    matched_text=f"[graph-derived via {rel_type} from '{match.entity_name}']",
                    is_graph_derived=True,
                ))
                direct_ids.add(neighbour_id)  # avoid duplication

        return derived

    def _classify_tier_with_evidence(
        self,
        responsibility: StructuredRequirement,
    ) -> TierEvidence:
        """
        Classify PRIMARY/SECONDARY/SITUATIONAL with full evidence record.

        Interpretation confidence reflects how strongly the text supports the tier.
        Entity-match confidence is NOT used here (kept separate).
        """
        text_lower = responsibility.text.lower()

        # Collect matching signals per tier (using word boundaries to avoid partial matches like 'develop' in 'development')
        def find_signals(signals: List[str], text: str) -> List[str]:
            return [s for s in signals if re.search(rf'\b{re.escape(s)}\b', text)]

        situational_found = find_signals(self._situational_signals, text_lower)
        secondary_found = find_signals(self._secondary_signals, text_lower)
        primary_found = find_signals(self._primary_signals, text_lower)

        # Tier assignment (situational > secondary precedence when both)
        if situational_found:
            return TierEvidence(
                tier=ResponsibilityTier.SITUATIONAL,
                signals_found=situational_found,
                interpretation_confidence=ConfidenceLevel.HIGH,
                rationale=f"Situational signals: {', '.join(situational_found[:3])}",
            )

        if secondary_found and not primary_found:
            return TierEvidence(
                tier=ResponsibilityTier.SECONDARY,
                signals_found=secondary_found,
                interpretation_confidence=ConfidenceLevel.HIGH,
                rationale=f"Secondary signals: {', '.join(secondary_found[:3])}",
            )

        if primary_found:
            confidence = ConfidenceLevel.HIGH if len(primary_found) >= 2 else ConfidenceLevel.MEDIUM
            return TierEvidence(
                tier=ResponsibilityTier.PRIMARY,
                signals_found=primary_found,
                interpretation_confidence=confidence,
                rationale=f"Primary signals: {', '.join(primary_found[:3])}",
            )

        if secondary_found:
            # Both primary and secondary found; call it secondary (conservative)
            return TierEvidence(
                tier=ResponsibilityTier.SECONDARY,
                signals_found=secondary_found,
                interpretation_confidence=ConfidenceLevel.MEDIUM,
                rationale=f"Mixed signals; defaulting to SECONDARY. found: {', '.join(secondary_found[:2])}",
            )

        # No clear signals — default PRIMARY with low confidence
        return TierEvidence(
            tier=ResponsibilityTier.PRIMARY,
            signals_found=[],
            interpretation_confidence=ConfidenceLevel.LOW,
            rationale="No clear tier signals found; defaulted to PRIMARY (low confidence)",
        )

    def _map_to_capabilities(
        self,
        responsibility: StructuredRequirement,
        all_requirements: List[StructuredRequirement],
        entity_matches: List[EntityMatch],
    ) -> List[str]:
        """
        Map responsibility to related REQUIREMENT IDs via entity overlap.

        Only direct-match entities are used for capability mapping to avoid
        over-expanding via tenuous graph-derived links.
        """
        if not entity_matches:
            return []

        direct_entity_ids = {
            m.entity_id for m in entity_matches if not m.is_graph_derived
        }

        capability_ids: Set[str] = set()
        for req in all_requirements:
            if req.clause_type != ClauseType.REQUIREMENT:
                continue
            if req.requirement_id == responsibility.requirement_id:
                continue
            req_entity_ids = set(req.matched_entities)
            if direct_entity_ids & req_entity_ids:  # non-empty intersection
                capability_ids.add(req.requirement_id)

        return sorted(capability_ids)

    def _assess_interpretation_confidence(
        self,
        tier_evidence: TierEvidence,
        entity_matches: List[EntityMatch],
        capabilities: List[str],
    ) -> ConfidenceLevel:
        """
        Assess overall interpretation confidence.

        Combines tier evidence strength with capability mapping evidence.
        Entity-match confidence is NOT directly used here (different concept).
        """
        base = tier_evidence.interpretation_confidence

        # Downgrade if we found no entity matches at all
        if not entity_matches:
            if base == ConfidenceLevel.HIGH:
                return ConfidenceLevel.MEDIUM
            elif base == ConfidenceLevel.MEDIUM:
                return ConfidenceLevel.LOW

        # Upgrade if we have strong tier signals AND entity support
        direct_matches = [m for m in entity_matches if not m.is_graph_derived]
        if (base == ConfidenceLevel.MEDIUM
                and len(tier_evidence.signals_found) >= 2
                and len(direct_matches) >= 1):
            return ConfidenceLevel.HIGH

        return base

    def _build_rationale(
        self,
        tier_evidence: TierEvidence,
        entity_matches: List[EntityMatch],
        graph_derived: List[EntityMatch],
        capabilities: List[str],
        all_requirements: List[StructuredRequirement],
    ) -> str:
        """
        Build a human-readable rationale that clearly separates:
        - Tier classification evidence
        - Direct EKG matches
        - Graph-derived expansions (clearly labelled)
        - Capability mapping
        """
        parts: List[str] = []

        # Tier rationale
        parts.append(f"[Tier {tier_evidence.tier.value}] {tier_evidence.rationale}")

        # Direct EKG entity evidence
        if entity_matches:
            direct = [m for m in entity_matches if not m.is_graph_derived]
            if direct:
                names_with_evidence = [
                    f"'{m.entity_name}' (matched: '{m.matched_text}', conf={m.match_confidence:.2f})"
                    for m in direct[:4]
                ]
                parts.append(f"Direct entity matches: {'; '.join(names_with_evidence)}")

        # Graph-derived expansions — always clearly labelled
        if graph_derived:
            derived_names = [m.entity_name for m in graph_derived[:3]]
            parts.append(
                f"Graph-derived context (not from JD text): {', '.join(derived_names)}"
            )

        # Capability mapping
        if capabilities:
            req_lookup = {r.requirement_id: r.text[:50] for r in all_requirements}
            cap_snippets = [
                f"'{req_lookup.get(cid, cid)}'" for cid in capabilities[:3]
            ]
            parts.append(f"Linked requirements: {', '.join(cap_snippets)}")
        else:
            parts.append("No linked requirements identified via entity overlap")

        return " | ".join(parts)

    # ------------------------------------------------------------------
    # Tier 2 — Optional LLM hypothesis (extension point)
    # ------------------------------------------------------------------

    def _attempt_llm_hypothesis(
        self,
        responsibility: StructuredRequirement,
    ) -> Optional[LLMHypothesis]:
        """
        Attempt an optional LLM hypothesis if a hook was provided.

        CRITICAL:
        - Never called unless `_llm_hook` is set by the caller.
        - Output is always `is_confirmed=False`.
        - Malformed or failed output silently returns None (deterministic
          result is never corrupted).
        - No network call; no model download; no dependency injection.
        """
        if self._llm_hook is None:
            return None

        try:
            hypothesis_text = self._llm_hook(responsibility.text)
            if not isinstance(hypothesis_text, str) or not hypothesis_text.strip():
                logger.warning("[Interpretation] LLM hook returned empty/invalid output")
                return None

            logger.info(
                "[Interpretation] Tier 2 LLM hypothesis generated for %s",
                responsibility.requirement_id,
            )
            return LLMHypothesis(
                hypothesis_text=hypothesis_text.strip(),
                model_name="caller-supplied-hook",
                is_confirmed=False,
            )
        except Exception as exc:
            logger.warning(
                "[Interpretation] LLM hook failed for %s: %s",
                responsibility.requirement_id,
                exc,
            )
            return None

    # ------------------------------------------------------------------
    # Tier 3 — TA/HR confirmed interpretation
    # ------------------------------------------------------------------

    def _extract_ta_facts(
        self,
        responsibility: StructuredRequirement,
        clarification_context: Dict[str, str],
    ) -> List[TAConfirmedFact]:
        """
        Extract explicitly supplied TA/HR facts relevant to this responsibility.

        Facts are accepted ONLY when the caller has explicitly provided them in
        `clarification_context`. They are kept strictly separate from JD evidence.
        """
        facts: List[TAConfirmedFact] = []

        # Look for answers keyed by this responsibility's ID
        answer = clarification_context.get(responsibility.requirement_id)
        if not answer:
            return facts

        # Validate the answer is non-trivial before accepting as a fact
        validated, reason = _validate_clarification_answer(answer, context="responsibility")
        if not validated:
            logger.debug(
                "[Interpretation] Tier 3 answer rejected for %s: %s",
                responsibility.requirement_id,
                reason,
            )
            return facts

        facts.append(TAConfirmedFact(
            fact_text=f"TA confirmed: {answer.strip()}",
            confirmed_by="TA/HR via clarification context",
            source_answer=answer.strip(),
        ))
        logger.info(
            "[Interpretation] Tier 3 fact accepted for %s",
            responsibility.requirement_id,
        )
        return facts


# ---------------------------------------------------------------------------
# Clarification answer validation (used by interpreter and ambiguity re-analysis)
# ---------------------------------------------------------------------------

# Placeholder / non-answer strings
_NON_ANSWERS = frozenset({
    "skip", "unknown", "unclear", "n/a", "not applicable",
    "no answer", "none", "not sure", "tbd", "to be determined",
    "not provided", "no comment",
})

# Minimum substantive length for an answer to be considered resolved
_MIN_ANSWER_LENGTH = 15


def _validate_clarification_answer(
    answer: str,
    context: str = "generic",
) -> tuple[bool, str]:
    """
    Validate whether a clarification answer adequately addresses a finding.

    Conservative deterministic validation — no LLM required.
    Returns (is_valid, reason_if_invalid).

    Rules:
    1. Non-empty string required.
    2. Must not be a placeholder/non-answer.
    3. Must meet minimum substantive length.
    4. Additional context-specific checks applied when `context` is provided.
    """
    if not answer or not answer.strip():
        return False, "Answer is empty"

    stripped = answer.strip()
    lower = stripped.lower()

    if lower in _NON_ANSWERS:
        return False, f"Answer is a placeholder: '{stripped}'"

    # Check for single-word answers that are likely non-substantive
    words = stripped.split()
    if len(words) == 1 and len(stripped) < 5:
        return False, f"Answer too brief: '{stripped}'"

    if len(stripped) < _MIN_ANSWER_LENGTH:
        return False, f"Answer too short ({len(stripped)} chars < {_MIN_ANSWER_LENGTH})"

    # Context-specific checks
    if context == "tool":
        # For tool ambiguities, an answer should mention at least one recognisable
        # tool-like term (contains a proper noun or version number heuristic)
        has_tool_like_term = bool(
            re.search(r'\b[A-Z][A-Za-z0-9+#.]{2,}\b|\b\d+\.\d+\b', stripped)
        )
        if not has_tool_like_term:
            return False, "Tool answer lacks specific tool names or versions"

    if context == "experience":
        # Experience answers should contain a number or level term
        has_years_or_level = bool(
            re.search(
                r'\b\d+\b|junior|mid|senior|lead|principal|entry',
                stripped, re.IGNORECASE
            )
        )
        if not has_years_or_level:
            return False, "Experience answer lacks a quantity or level"

    return True, ""


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def create_interpreter(
    llm_hook: Optional[Callable[[str], str]] = None,
) -> ResponsibilityInterpreter:
    """
    Factory function for ResponsibilityInterpreter.

    Args:
        llm_hook: Optional Tier 2 LLM callable. Omit for deterministic-only mode.
    """
    return ResponsibilityInterpreter(llm_hook=llm_hook)

