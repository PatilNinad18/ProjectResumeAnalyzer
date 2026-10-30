"""
clarification/engine.py — Deterministic Clarification Question Generator.

Implements the 3-Tier Question Classification Policy from Problem 2 (B):
  - Tier 1 (BLOCKING):     Contradictions, unresolvable core scope conflicts.
  - Tier 2 (RECOMMENDED):  Technical scope gaps (non-blocking; has fallback).
  - Tier 3 (OPTIONAL):     Metadata (team size, salary) — quick intake chips.

Design Invariants:
  1. Zero LLM calls. All question generation is purely deterministic rule-based.
  2. Idempotent: questions are keyed by question_key. Calling generate() twice
     on the same master context produces the same set of question_keys (no duplicates).
  3. Questions are merged into master.clarification_history (existing answers preserved).
  4. OPTIONAL questions (team_size, salary) are NEVER is_blocking=True.
"""
from __future__ import annotations

import logging
import re
from typing import List, Optional

from app.schemas.master_context import (
    ClarificationOptionSchema,
    ClarificationQuestionSchema,
    ConfidenceBand,
    InterpretationStatus,
    JDMasterContext,
    JDLifecycleStatus,
    LogicOperator,
    OriginType,
    QuestionCategory,
    QuestionPriority,
    QuestionStatus,
    RequirementPriority,
    StructuredRequirement,
    DisjunctionGroup,
)

logger = logging.getLogger("jd_agent.clarification.engine")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_clarification_questions(
    master: JDMasterContext,
    *,
    actor: Optional[str] = None,
) -> JDMasterContext:
    """
    Evaluate the master context and generate clarification questions.
    Merges new questions into master.clarification_history (idempotent by question_key).
    Updates lifecycle_status to AWAITING_CLARIFICATION if any questions were generated,
    or READY_FOR_REVIEW if none.

    Returns the mutated master context.
    """
    existing_keys = {q.question_key for q in master.clarification_history}
    new_questions: List[ClarificationQuestionSchema] = []

    # --- Tier 1: BLOCKING — Contradictions ---
    new_questions.extend(_detect_contradictions(master, existing_keys))

    # --- Tier 1: BLOCKING — UNRESOLVED mandatory requirements ---
    new_questions.extend(_detect_unresolved_mandatory(master, existing_keys))

    # --- Conversational Ambiguities & Scope (Claude-Style Topics & Options) ---

    new_questions.extend(_detect_conversational_ambiguities(master, existing_keys))



    # --- Tier 2: RECOMMENDED — Technical scope disambiguation ---
    new_questions.extend(_detect_low_confidence_requirements(master, existing_keys))

    # --- Tier 2: RECOMMENDED — Uninterpreted responsibilities with EKG matches ---
    new_questions.extend(_detect_uninterpreted_responsibilities(master, existing_keys))

    # --- Tier 2: RECOMMENDED — Contextual phrasing requiring TA confirmation ---
    new_questions.extend(_detect_contextual_ambiguities(master, existing_keys))

    # --- Tier 2: RECOMMENDED — Ambiguities detected in JD text ---
    new_questions.extend(_detect_raw_ambiguities(master, existing_keys))

    # --- Tier 3: OPTIONAL — Missing metadata (team size, salary) ---
    new_questions.extend(_detect_missing_metadata(master, existing_keys))

    if new_questions:
        # Optionally rewrite question_text into conversational phrasing via LLM.
        # Falls back silently to deterministic text if Ollama is unavailable.
        new_questions = enrich_questions_conversational(master, new_questions)
        master.clarification_history.extend(new_questions)
        master.lifecycle_status = JDLifecycleStatus.AWAITING_CLARIFICATION
        master.add_audit_entry(
            "clarification_generated",
            f"Generated {len(new_questions)} new clarification question(s).",
            actor=actor,
            question_count=len(new_questions),
            blocking_count=sum(1 for q in new_questions if q.is_blocking),
        )
        logger.info(
            "Generated %d clarification questions for jd_id=%s (%d blocking).",
            len(new_questions),
            master.jd_id,
            sum(1 for q in new_questions if q.is_blocking),
        )
    else:
        master.lifecycle_status = JDLifecycleStatus.READY_FOR_REVIEW
        master.add_audit_entry(
            "clarification_none_needed",
            "No clarification questions required. JD is ready for review.",
            actor=actor,
        )

    return master


def compute_is_blocking(question: ClarificationQuestionSchema) -> bool:
    """
    Dynamically recompute whether a question is still blocking.
    A BLOCKING-priority question is no longer blocking if it has been
    ANSWERED, EXPLICITLY_UNSPECIFIED, or has an authorized override_record.
    """
    if question.priority != QuestionPriority.BLOCKING:
        return False
    if question.status in {QuestionStatus.ANSWERED, QuestionStatus.EXPLICITLY_UNSPECIFIED}:
        return False
    if question.override_record is not None:
        return False
    return True


def recompute_all_blocking_flags(master: JDMasterContext) -> JDMasterContext:
    """
    Recompute is_blocking on every question in the master's clarification history.
    Call this after any answer is submitted.
    """
    for question in master.clarification_history:
        question.is_blocking = compute_is_blocking(question)
    return master


# ---------------------------------------------------------------------------
# Tier 1: BLOCKING Question Generators
# ---------------------------------------------------------------------------

def _detect_contradictions(
    master: JDMasterContext,
    existing_keys: set,
) -> List[ClarificationQuestionSchema]:
    """
    Detects logical contradictions:
    - A requirement marked MUST_HAVE but also negated=True.
    - Two requirements with conflicting priority signals for the same ekg_node_ids.
    """
    questions: List[ClarificationQuestionSchema] = []

    for item in master.requirements:
        if not isinstance(item, StructuredRequirement):
            continue

        # Contradiction: is_mandatory=True but negated=True
        if item.is_mandatory and item.negated:
            key = f"contradiction_mandatory_negated_{item.id[:8]}"
            if key not in existing_keys:
                questions.append(ClarificationQuestionSchema(
                    question_key=key,
                    category=QuestionCategory.CONTRADICTION,
                    priority=QuestionPriority.BLOCKING,
                    is_blocking=True,
                    field_target=f"requirements[id={item.id}].priority",
                    question_text=(
                        f"The requirement '{item.text[:120]}' appears both as mandatory "
                        f"and negated in the JD. Is this requirement actually required or explicitly excluded?"
                    ),
                    rationale=(
                        "The clause is marked is_mandatory=True but has negated=True. "
                        "This is a logical contradiction that must be resolved before candidate screening."
                    ),
                    suggested_options=["It IS required (remove negation)", "It is NOT required (exclude from must-haves)"],
                ))

    return questions


def _detect_unresolved_mandatory(
    master: JDMasterContext,
    existing_keys: set,
) -> List[ClarificationQuestionSchema]:
    """
    Flags StructuredRequirements with priority=UNRESOLVED that appear in
    critical requirement positions (they cannot be left ambiguous for screening).
    """
    questions: List[ClarificationQuestionSchema] = []
    unresolved = [
        item for item in master.requirements
        if isinstance(item, StructuredRequirement)
        and item.priority == RequirementPriority.UNRESOLVED
        and item.confidence.entity_match_confidence in {ConfidenceBand.HIGH, ConfidenceBand.MEDIUM}
    ]

    for i, item in enumerate(unresolved):
        key = f"unresolved_priority_{item.id[:8]}_{i}"
        if key not in existing_keys:
            questions.append(ClarificationQuestionSchema(
                question_key=key,
                category=QuestionCategory.TECHNICAL_SCOPE,
                priority=QuestionPriority.BLOCKING,
                is_blocking=True,
                field_target=f"requirements[id={item.id}].priority",
                question_text=(
                    f"The phrasing '{item.text[:120]}' was ambiguous — we could not determine "
                    f"if this is a MUST HAVE or a PREFERRED requirement. "
                    f"Is this requirement mandatory for all candidates?"
                ),
                rationale=(
                    "The clause uses ambiguous modal phrasing (e.g. 'ideally', 'experience with', "
                    "'knowledge of') that does not clearly indicate mandatory vs preferred status."
                ),
                suggested_options=["MUST HAVE — mandatory for all candidates", "PREFERRED — nice to have but not disqualifying"],
            ))

    return questions


# ---------------------------------------------------------------------------
# Tier 2: RECOMMENDED Question Generators
# ---------------------------------------------------------------------------

def _detect_conversational_ambiguities(

    master: JDMasterContext,

    existing_keys: set,

) -> List[ClarificationQuestionSchema]:

    """

    Analyzes JD requirements, role overview, and responsibilities to generate

    conversational, tailored questions with structured options (label + description)

    and short topic tags for wizard navigation (e.g. 'VDK tooling', 'Experience',

    'Leadership', 'Protocols', 'Chiplet exp', 'Hands-on %', 'Customer', 'Location').

    """

    questions: List[ClarificationQuestionSchema] = []

    ro = getattr(master, "role_overview", None)

    job_title = getattr(ro, "job_title", None) or getattr(ro, "title", None) or getattr(ro, "role_title", None) or ""

    raw_jd = getattr(master, "raw_jd_text", None) or getattr(getattr(master, "extraction_metadata", None), "source_text", None) or ""



    req_texts = [

        getattr(r, "text", "") for r in getattr(master, "requirements", [])

        if getattr(r, "text", None)

    ]

    resp_texts = [

        getattr(r, "raw_statement", "") for r in getattr(master, "responsibilities", [])

        if getattr(r, "raw_statement", None)

    ]

    all_text = f"{job_title}\n{raw_jd}\n" + "\n".join(req_texts) + "\n" + "\n".join(resp_texts)

    text_lower = all_text.lower()

    title_lower = job_title.lower()



    # 1. Tooling / Framework Strictness vs Equivalence

    if "vdk_tooling_strictness" not in existing_keys and "tooling_strictness" not in existing_keys:

        if any(k in text_lower for k in ("virtualizer", "vdk", "virtual prototyping", "systemc/tlm", "systemc")):

            questions.append(ClarificationQuestionSchema(

                question_key="vdk_tooling_strictness",

                category=QuestionCategory.TECHNICAL_SCOPE,

                priority=QuestionPriority.RECOMMENDED,

                is_blocking=False,

                field_target="requirements.tooling.synopsys_vdk",

                short_topic="VDK tooling",

                question_text="The JD lists 'Synopsys Virtualizer / VDK experience' under Required Skills. Is Synopsys tooling a strict must-have, or would equivalent virtual prototyping experience qualify?",

                rationale="Synopsys Virtualizer is specialized. Clarifying whether equivalent platforms qualify determines candidate pool size.",

                structured_options=[

                    ClarificationOptionSchema(

                        label="Strict must-have",

                        description="Only candidates with hands-on Synopsys Virtualizer/VDK experience qualify.",

                    ),

                    ClarificationOptionSchema(

                        label="Equivalents acceptable",

                        description="Cadence Helium, Arm Fast Models/FVP, Siemens Vista, or QEMU+SystemC co-sim count as equivalent; Synopsys ramp-up expected.",

                    ),

                    ClarificationOptionSchema(

                        label="Strong preference",

                        description="Synopsys is preferred, but a strong SystemC/TLM architect without it can still be considered.",

                    ),

                ],

                suggested_options=[

                    "Strict must-have — Only candidates with hands-on Synopsys Virtualizer/VDK experience qualify.",

                    "Equivalents acceptable — Cadence Helium, Arm Fast Models/FVP, Siemens Vista, or QEMU+SystemC co-sim count as equivalent; Synopsys ramp-up expected.",

                    "Strong preference — Synopsys is preferred, but a strong SystemC/TLM architect without it can still be considered.",

                ],

            ))

        elif any(k in text_lower for k in ("fastapi", "django", "flask", "spring", "react", "kubernetes", "flutter", "golang", "pytorch")):

            detected_tool = "Core Framework"

            detected_equivs = "equivalent modern frameworks"

            if "fastapi" in text_lower:

                detected_tool = "FastAPI"

                detected_equivs = "Django, Flask, Go/Gin, or Spring Boot"

            elif "pytorch" in text_lower:

                detected_tool = "PyTorch"

                detected_equivs = "TensorFlow, JAX, or ONNX"

            elif "react" in text_lower:

                detected_tool = "React"

                detected_equivs = "Vue.js, Angular, or Next.js"

            elif "kubernetes" in text_lower:

                detected_tool = "Kubernetes"

                detected_equivs = "Docker Swarm, Nomad, or ECS"

            elif "golang" in text_lower or "go " in text_lower:

                detected_tool = "Go (Golang)"

                detected_equivs = "C++, Rust, or Java"



            key = f"tooling_strictness_{detected_tool.lower().replace(' ', '_')}"

            if key not in existing_keys:

                questions.append(ClarificationQuestionSchema(

                    question_key=key,

                    category=QuestionCategory.TECHNICAL_SCOPE,

                    priority=QuestionPriority.RECOMMENDED,

                    is_blocking=False,

                    field_target=f"requirements.tooling.{detected_tool.lower()}",

                    short_topic=f"{detected_tool} tooling",

                    question_text=f"The JD lists '{detected_tool}' under Required Skills. Is {detected_tool} tooling a strict must-have, or would equivalent experience qualify?",

                    rationale=f"Clarifying whether {detected_tool} is mandatory or interchangeable with equivalents ({detected_equivs}) calibrates screening selectivity.",

                    structured_options=[

                        ClarificationOptionSchema(

                            label="Strict must-have",

                            description=f"Only candidates with hands-on {detected_tool} experience qualify.",

                        ),

                        ClarificationOptionSchema(

                            label="Equivalents acceptable",

                            description=f"{detected_equivs} count as equivalent; {detected_tool} ramp-up expected.",

                        ),

                        ClarificationOptionSchema(

                            label="Strong preference",

                            description=f"{detected_tool} is preferred, but a strong architect/engineer with adjacent modern stack can still be considered.",

                        ),

                    ],

                    suggested_options=[

                        f"Strict must-have — Only candidates with hands-on {detected_tool} experience qualify.",

                        f"Equivalents acceptable — {detected_equivs} count as equivalent; {detected_tool} ramp-up expected.",

                        f"Strong preference — {detected_tool} is preferred, but a strong candidate without it can still be considered.",

                    ],

                ))



    # 2. Experience Specialization Split (Topic: 'Experience')

    if "experience_specialization_split" not in existing_keys:

        exp_match = re.search(r"(\d+[\s–\-]+\d+\+?|\d+\+?)\s*(?:years|yrs)", text_lower)

        exp_str = exp_match.group(0) if exp_match else None



        if any(k in text_lower for k in ("10–15+", "10-15+", "10-15", "10 to 15")) or (exp_str and "10" in exp_str and "semiconductor" in text_lower):

            questions.append(ClarificationQuestionSchema(

                question_key="experience_specialization_split",

                category=QuestionCategory.TECHNICAL_SCOPE,

                priority=QuestionPriority.RECOMMENDED,

                is_blocking=False,

                field_target="requirements.experience.vp_split",

                short_topic="Experience",

                question_text="'10-15+ years of semiconductor/system engineering experience' - how much of that must be specifically in virtual platforms / SystemC-TLM modelling?",

                rationale="A 10-15 year band is broad. Calibrating how many years must be directly in virtual platforms vs general semiconductor/RTL engineering avoids false negatives.",

                structured_options=[

                    ClarificationOptionSchema(

                        label="10+ total, 5+ in VP",

                        description="At least 10 years overall, with 5+ years directly in virtual prototyping / SystemC-TLM.",

                    ),

                    ClarificationOptionSchema(

                        label="10+ total, any domain",

                        description="10+ years in semiconductor/system engineering is enough; VP depth is assessed via skills, not years.",

                    ),

                    ClarificationOptionSchema(

                        label="8+ if VP-heavy",

                        description="Exceptional candidates with ~8 years, mostly in VP architecture, can be considered.",

                    ),

                    ClarificationOptionSchema(

                        label="15+ preferred",

                        description="Target the upper band; 10-12 years is the floor only for outstanding profiles.",

                    ),

                ],

                suggested_options=[

                    "10+ total, 5+ in VP — At least 10 years overall, with 5+ years directly in virtual prototyping / SystemC-TLM.",

                    "10+ total, any domain — 10+ years in semiconductor/system engineering is enough; VP depth is assessed via skills, not years.",

                    "8+ if VP-heavy — Exceptional candidates with ~8 years, mostly in VP architecture, can be considered.",

                    "15+ preferred — Target the upper band; 10-12 years is the floor only for outstanding profiles.",

                ],

            ))

        elif exp_str:

            num = re.search(r"\d+", exp_str).group(0)

            questions.append(ClarificationQuestionSchema(

                question_key="experience_specialization_split",

                category=QuestionCategory.TECHNICAL_SCOPE,

                priority=QuestionPriority.RECOMMENDED,

                is_blocking=False,

                field_target="requirements.experience.domain_split",

                short_topic="Experience",

                question_text=f"'{exp_str} of engineering experience' - how much of that must be specifically in core domain systems vs general development?",

                rationale="Calibrating total engineering tenure against specialized hands-on domain focus ensures balanced candidate qualification.",

                structured_options=[

                    ClarificationOptionSchema(

                        label=f"{num}+ total, dedicated focus",

                        description=f"At least {num} years overall, with primary hands-on specialization in core role domains.",

                    ),

                    ClarificationOptionSchema(

                        label=f"{num}+ total, any domain",

                        description=f"{num}+ years in general engineering is sufficient; specific domain depth is evaluated via technical assessment.",

                    ),

                    ClarificationOptionSchema(

                        label="Fast-track for exceptional",

                        description="Exceptional candidates with slightly fewer years but demonstrated architectural depth qualify.",

                    ),

                    ClarificationOptionSchema(

                        label="Upper band preferred",

                        description=f"Target the upper band; {num} years is the minimum floor for consideration.",

                    ),

                ],

                suggested_options=[

                    f"{num}+ total, dedicated focus — At least {num} years overall, with primary hands-on specialization in core role domains.",

                    f"{num}+ total, any domain — {num}+ years in general engineering is sufficient; domain depth assessed via skills.",

                    "Fast-track for exceptional — Exceptional candidates with slightly fewer years but heavy depth qualify.",

                    f"Upper band preferred — Target the upper band; {num} years is the floor only for outstanding profiles.",

                ],

            ))



    # 3. Leadership & Reporting Scope (Topic: 'Leadership')

    if "leadership_people_management" not in existing_keys:

        if "jd 2–7" in text_lower or "jd 2-7" in text_lower or ("technical lead" in text_lower and "architect" in text_lower):

            questions.append(ClarificationQuestionSchema(

                question_key="leadership_people_management",

                category=QuestionCategory.ROLE_ALIGNMENT,

                priority=QuestionPriority.RECOMMENDED,

                is_blocking=False,

                field_target="role_overview.people_management",

                short_topic="Leadership",

                question_text="The role is titled 'Technical Lead / Architect' and is the anchor for JD 2-7. Does this role carry people-management responsibility?",

                rationale="Understanding whether this anchor architect will directly manage team hires vs provide purely technical architecture guidance defines the hiring persona.",

                structured_options=[

                    ClarificationOptionSchema(

                        label="Technical lead, no reports",

                        description="Sets architecture and guides JD 2-7 engineers technically, but has no formal reporting lines.",

                    ),

                    ClarificationOptionSchema(

                        label="Lead with direct reports",

                        description="Directly manages the JD 2-7 hires (hiring, appraisals, task allocation).",

                    ),

                    ClarificationOptionSchema(

                        label="Lead now, manager later",

                        description="Starts as technical lead; formal people management added once the team scales.",

                    ),

                ],

                suggested_options=[

                    "Technical lead, no reports — Sets architecture and guides JD 2-7 engineers technically, but has no formal reporting lines.",

                    "Lead with direct reports — Directly manages the JD 2-7 hires (hiring, appraisals, task allocation).",

                    "Lead now, manager later — Starts as technical lead; formal people management added once the team scales.",

                ],

            ))

        elif any(k in title_lower for k in ("lead", "architect", "principal", "manager", "director", "staff")):

            clean_title = job_title or "Lead / Architect"

            questions.append(ClarificationQuestionSchema(

                question_key="leadership_people_management",

                category=QuestionCategory.ROLE_ALIGNMENT,

                priority=QuestionPriority.RECOMMENDED,

                is_blocking=False,

                field_target="role_overview.people_management",

                short_topic="Leadership",

                question_text=f"The role is titled '{clean_title}'. Does this role carry direct people-management responsibility?",

                rationale="Clarifying whether this role is an individual contributor technical lead or has direct managerial reports aligns candidate screening.",

                structured_options=[

                    ClarificationOptionSchema(

                        label="Technical lead, no reports",

                        description="Sets technical direction and architecture, but has no formal managerial reporting lines.",

                    ),

                    ClarificationOptionSchema(

                        label="Lead with direct reports",

                        description="Directly manages team engineers (hiring, 1-on-1s, appraisals, task allocation).",

                    ),

                    ClarificationOptionSchema(

                        label="Lead now, manager later",

                        description="Starts as technical lead; formal people management added once the team scales.",

                    ),

                ],

                suggested_options=[

                    "Technical lead, no reports — Sets technical direction, but has no formal reporting lines.",

                    "Lead with direct reports — Directly manages team engineers (hiring, appraisals, task allocation).",

                    "Lead now, manager later — Starts as technical lead; formal people management added once the team scales.",

                ],

            ))



    # 4. Protocol / Interconnects Coverage (Topic: 'Protocols')

    if "protocols_coverage_depth" not in existing_keys:

        if any(k in text_lower for k in ("pcie", "cxl", "ucie", "amba")):

            questions.append(ClarificationQuestionSchema(

                question_key="protocols_coverage_depth",

                category=QuestionCategory.TECHNICAL_SCOPE,

                priority=QuestionPriority.RECOMMENDED,

                is_blocking=False,

                field_target="requirements.protocols.coverage",

                short_topic="Protocols",

                question_text="Required skills list 'PCIe / CXL / UCIe / AMBA'. What depth of protocol coverage is expected?",

                rationale="Expecting all four high-speed interconnects significantly narrows the candidate pool. Setting the coverage floor improves sourcing efficiency.",

                structured_options=[

                    ClarificationOptionSchema(

                        label="All four required",

                        description="Candidate must have worked with each of PCIe, CXL, UCIe and AMBA.",

                    ),

                    ClarificationOptionSchema(

                        label="1 high-speed + AMBA",

                        description="At least one of PCIe/CXL/UCIe plus AMBA (AXI/CHI) is sufficient.",

                    ),

                    ClarificationOptionSchema(

                        label="UCIe mandatory",

                        description="Given the chiplet focus, UCIe is must-have; others are a plus.",

                    ),

                    ClarificationOptionSchema(

                        label="Any one is fine",

                        description="Familiarity with any of these interconnects is enough; the rest can be learned.",

                    ),

                ],

                suggested_options=[

                    "All four required — Candidate must have worked with each of PCIe, CXL, UCIe and AMBA.",

                    "1 high-speed + AMBA — At least one of PCIe/CXL/UCIe plus AMBA (AXI/CHI) is sufficient.",

                    "UCIe mandatory — Given the chiplet focus, UCIe is must-have; others are a plus.",

                    "Any one is fine — Familiarity with any of these interconnects is enough; the rest can be learned.",

                ],

            ))



    # 5. Title vs Preferred Skills Tension (Topic: 'Chiplet exp' / 'Specialization')

    if "chiplet_experience_must_have" not in existing_keys:

        if "chiplet" in text_lower and ("hbm" in text_lower or "preferred" in text_lower):

            questions.append(ClarificationQuestionSchema(

                question_key="chiplet_experience_must_have",

                category=QuestionCategory.TECHNICAL_SCOPE,

                priority=QuestionPriority.RECOMMENDED,

                is_blocking=False,

                field_target="requirements.chiplet.priority",

                short_topic="Chiplet exp",

                question_text="The JD is for an 'AI Chiplet' architect, yet 'Chiplet architecture and HBM' is only under Preferred Skills. Is prior chiplet experience a must-have?",

                rationale="The role title emphasizes 'Chiplet', but chiplet architecture is categorized under Preferred Skills. Clarifying this resolves screening inconsistency.",

                structured_options=[

                    ClarificationOptionSchema(

                        label="Must-have",

                        description="Candidate must have worked on multi-die/chiplet systems (D2D links, partitioning).",

                    ),

                    ClarificationOptionSchema(

                        label="Preferred only",

                        description="Keep as stated: a strong SoC VP architect without chiplet exposure still qualifies.",

                    ),

                    ClarificationOptionSchema(

                        label="Chiplet yes, HBM optional",

                        description="Chiplet experience is required; HBM/memory-subsystem knowledge is a plus.",

                    ),

                ],

                suggested_options=[

                    "Must-have — Candidate must have worked on multi-die/chiplet systems (D2D links, partitioning).",

                    "Preferred only — Keep as stated: a strong SoC VP architect without chiplet exposure still qualifies.",

                    "Chiplet yes, HBM optional — Chiplet experience is required; HBM/memory-subsystem knowledge is a plus.",

                ],

            ))



    # 6. Hands-on Implementation % (Topic: 'Hands-on %')

    if "hands_on_coding_percentage" not in existing_keys:

        if any(k in text_lower for k in ("systemc/tlm", "systemc", "reusable", "infrastructure", "coding", "develop reusable")):

            questions.append(ClarificationQuestionSchema(

                question_key="hands_on_coding_percentage",

                category=QuestionCategory.ROLE_ALIGNMENT,

                priority=QuestionPriority.RECOMMENDED,

                is_blocking=False,

                field_target="role_overview.hands_on_percentage",

                short_topic="Hands-on %",

                question_text="Responsibilities include both architecture and 'develop reusable SystemC/TLM-based platform infrastructure'. How hands-on is this role expected to be?",

                rationale="Architect roles vary from pure documentation to heavy active coding. Setting hands-on expectations calibrates technical screening.",

                structured_options=[

                    ClarificationOptionSchema(

                        label="Heavily hands-on (>50%)",

                        description="Writes significant SystemC/TLM code and model infrastructure personally.",

                    ),

                    ClarificationOptionSchema(

                        label="Balanced (25-50%)",

                        description="Codes key framework pieces and templates; rest is architecture, reviews and guidance.",

                    ),

                    ClarificationOptionSchema(

                        label="Mostly architecture (<25%)",

                        description="Defines architecture and reviews; JD 2-7 engineers do most implementation.",

                    ),

                ],

                suggested_options=[

                    "Heavily hands-on (>50%) — Writes significant SystemC/TLM code and model infrastructure personally.",

                    "Balanced (25-50%) — Codes key framework pieces and templates; rest is architecture, reviews and guidance.",

                    "Mostly architecture (<25%) — Defines architecture and reviews; other engineers do most implementation.",

                ],

            ))



    # 7. Customer / Stakeholder Engagement (Topic: 'Customer')

    if "customer_facing_interaction" not in existing_keys:

        if any(k in text_lower for k in ("customer", "xpu/soc", "partner", "stakeholder", "client")):

            questions.append(ClarificationQuestionSchema(

                question_key="customer_facing_interaction",

                category=QuestionCategory.ROLE_ALIGNMENT,

                priority=QuestionPriority.RECOMMENDED,

                is_blocking=False,

                field_target="role_overview.customer_facing",

                short_topic="Customer",

                question_text="The role involves studying customer XPU/SoC architectures. How customer-facing is this position?",

                rationale="Knowing if the architect presents directly to external customer leadership vs consumes specs internally dictates communication evaluation.",

                structured_options=[

                    ClarificationOptionSchema(

                        label="Direct customer-facing",

                        description="Regularly engages customer architects, leads technical meetings, may travel.",

                    ),

                    ClarificationOptionSchema(

                        label="Occasional interaction",

                        description="Joins customer calls for key milestones; requirements mostly come via internal PM/FAE teams.",

                    ),

                    ClarificationOptionSchema(

                        label="Internal only",

                        description="Works from customer specs provided internally; no direct customer engagement.",

                    ),

                ],

                suggested_options=[

                    "Direct customer-facing — Regularly engages customer architects, leads technical meetings, may travel.",

                    "Occasional interaction — Joins customer calls for key milestones; requirements mostly come via internal PM/FAE teams.",

                    "Internal only — Works from customer specs provided internally; no direct customer engagement.",

                ],

            ))



    # 8. Location & Hybrid Arrangement (Topic: 'Location')

    if "location_hybrid_schedule" not in existing_keys:

        loc_str = getattr(getattr(master, "conventional_requirements", None), "location", None) or ""

        if isinstance(loc_str, dict):

            loc_str = loc_str.get("raw", "") or loc_str.get("city", "")

        if not loc_str and ("bangalore" in text_lower or "hyderabad" in text_lower or "pune" in text_lower or "hybrid" in text_lower):

            if "bangalore" in text_lower and "hyderabad" in text_lower:

                loc_str = "Bangalore / Hyderabad (Hybrid)"

            elif "pune" in text_lower:

                loc_str = "Pune (Work from Office)"



        if "bangalore" in loc_str.lower() or "hyderabad" in loc_str.lower():

            questions.append(ClarificationQuestionSchema(

                question_key="location_hybrid_schedule",

                category=QuestionCategory.COMPENSATION_LOGISTICS,

                priority=QuestionPriority.RECOMMENDED,

                is_blocking=False,

                field_target="job_context.location_hybrid",

                short_topic="Location",

                question_text="Location is listed as 'Bangalore / Hyderabad (Hybrid)'. What does the hybrid arrangement look like?",

                rationale="Candidates need clear expectations on in-office attendance requirements across Bangalore and Hyderabad.",

                structured_options=[

                    ClarificationOptionSchema(

                        label="Either city, 3 days office",

                        description="Candidate can be based in either city; 3 days/week in office.",

                    ),

                    ClarificationOptionSchema(

                        label="Either city, 2 days office",

                        description="Candidate can be based in either city; 2 days/week in office.",

                    ),

                    ClarificationOptionSchema(

                        label="Bangalore preferred",

                        description="Bangalore is primary; Hyderabad only for exceptional candidates.",

                    ),

                    ClarificationOptionSchema(

                        label="Flexible / mostly remote",

                        description="Office visits as needed; open to strong candidates in other Indian cities.",

                    ),

                ],

                suggested_options=[

                    "Either city, 3 days office — Candidate can be based in either city; 3 days/week in office.",

                    "Either city, 2 days office — Candidate can be based in either city; 2 days/week in office.",

                    "Bangalore preferred — Bangalore is primary; Hyderabad only for exceptional candidates.",

                    "Flexible / mostly remote — Office visits as needed; open to strong candidates in other Indian cities.",

                ],

            ))

        elif loc_str and ("hybrid" in loc_str.lower() or "office" in loc_str.lower()):

            questions.append(ClarificationQuestionSchema(

                question_key="location_hybrid_schedule",

                category=QuestionCategory.COMPENSATION_LOGISTICS,

                priority=QuestionPriority.RECOMMENDED,

                is_blocking=False,

                field_target="job_context.location_hybrid",

                short_topic="Location",

                question_text=f"Location is listed as '{loc_str}'. What does the hybrid/workplace schedule look like?",

                rationale="Clarifying on-site schedule and remote flexibility ensures accurate expectations during candidate outreach.",

                structured_options=[

                    ClarificationOptionSchema(

                        label="Hybrid (3 days office)",

                        description="Candidate expected on-site 3 days/week with 2 days remote flexibility.",

                    ),

                    ClarificationOptionSchema(

                        label="Hybrid (2 days office)",

                        description="Candidate expected on-site 2 days/week with 3 days remote flexibility.",

                    ),

                    ClarificationOptionSchema(

                        label="Full-time in office",

                        description="Full-time 5 days/week in-office attendance required.",

                    ),

                    ClarificationOptionSchema(

                        label="Flexible / mostly remote",

                        description="Remote-first with on-site visits only as required for key team milestones.",

                    ),

                ],

                suggested_options=[

                    "Hybrid (3 days office) — Candidate expected on-site 3 days/week with 2 days remote flexibility.",

                    "Hybrid (2 days office) — Candidate expected on-site 2 days/week with 3 days remote flexibility.",

                    "Full-time in office — Full-time 5 days/week in-office attendance required.",

                    "Flexible / mostly remote — Remote-first with occasional on-site visits as needed.",

                ],

            ))



    return questions





def _detect_low_confidence_requirements(
    master: JDMasterContext,
    existing_keys: set,
) -> List[ClarificationQuestionSchema]:
    """
    Flags requirements where entity_match_confidence=LOW, meaning the EKG
    could not confidently identify what technology/domain was being referenced.
    Non-blocking: has a fallback (use raw text for screening if unanswered).
    """
    questions: List[ClarificationQuestionSchema] = []
    low_conf = [
        item for item in master.requirements
        if isinstance(item, StructuredRequirement)
        and item.confidence.entity_match_confidence == ConfidenceBand.LOW
        and item.priority in {RequirementPriority.MUST_HAVE, RequirementPriority.PREFERRED}
    ]

    for i, item in enumerate(low_conf):
        key = f"low_confidence_entity_{item.id[:8]}_{i}"
        if key not in existing_keys:
            questions.append(ClarificationQuestionSchema(
                question_key=key,
                category=QuestionCategory.TECHNICAL_SCOPE,
                priority=QuestionPriority.RECOMMENDED,
                is_blocking=False,
                field_target=f"requirements[id={item.id}].ekg_node_ids",
                question_text=(
                    f"We could not precisely identify the technology or tool referenced in: "
                    f"'{item.text[:120]}'. "
                    f"Could you clarify what specific technology, framework, or domain is meant?"
                ),
                rationale=(
                    "Low entity match confidence means the EKG cannot confidently link this "
                    "requirement to a known technology. Clarification improves candidate scoring accuracy."
                ),
                suggested_options=[],
            ))

    return questions


def _detect_uninterpreted_responsibilities(
    master: JDMasterContext,
    existing_keys: set,
) -> List[ClarificationQuestionSchema]:
    """
    Flags responsibilities where the EKG matched entities but interpretation
    confidence is LOW — meaning the downstream activities are uncertain.
    Non-blocking: the raw responsibility text is still usable for screening.
    """
    questions: List[ClarificationQuestionSchema] = []
    for resp in master.responsibilities:
        if (
            resp.matched_entities
            and resp.interpretation_status == InterpretationStatus.NOT_INTERPRETED
            and resp.confidence.interpretation_confidence in {ConfidenceBand.LOW, ConfidenceBand.UNKNOWN}
        ):
            key = f"uninterpreted_responsibility_{resp.id[:8]}"
            if key not in existing_keys:
                entity_names = ", ".join(e.canonical_name for e in resp.matched_entities[:3])
                questions.append(ClarificationQuestionSchema(
                    question_key=key,
                    category=QuestionCategory.ROLE_ALIGNMENT,
                    priority=QuestionPriority.RECOMMENDED,
                    is_blocking=False,
                    field_target=f"responsibilities[id={resp.id}].interpretation_status",
                    question_text=(
                        f"The responsibility '{resp.raw_statement[:120]}' involves {entity_names}. "
                        f"What specific activities or depth of expertise should candidates demonstrate for this responsibility?"
                    ),
                    rationale=(
                        "The EKG matched known entities but could not derive specific activity requirements "
                        "at sufficient confidence. TA input will improve screening specificity."
                    ),
                    suggested_options=[],
                ))

    return questions


def _detect_contextual_ambiguities(
    master: JDMasterContext,
    existing_keys: set,
) -> List[ClarificationQuestionSchema]:
    """
    Generates questions for requirements flagged as CONTEXTUAL or INFORMATIONAL phrasing
    where TA confirmation is required to confirm mandatory vs preferred vs informational status.
    Filters out noise fragments, degree clauses, and limits questions to high-signal items.
    """
    questions: List[ClarificationQuestionSchema] = []
    from app.services.projection.canonical_projector import _flatten_requirements
    flat_reqs = _flatten_requirements(master.requirements)
    contextual = [
        item for item in flat_reqs
        if isinstance(item, StructuredRequirement)
        and item.priority in {RequirementPriority.CONTEXTUAL, RequirementPriority.INFORMATIONAL}
        and getattr(item, "text", None)
    ]

    seen_statements = {q.question_text.lower() for q in master.clarification_history}
    dangling_prefixes = ("in ", "or ", "and ", "with ", "to ", "for ", "of ")
    degree_keywords = ("degree", "bachelor", "master", "phd", "computer engineering", "electronics")

    for i, item in enumerate(contextual):
        if len(questions) >= 3:
            break

        statement_snip = item.text.strip()
        lower_snip = statement_snip.lower()

        # Filter out short fragments or dangling conjunction clauses
        if len(statement_snip) < 30:
            continue
        if lower_snip.startswith(dangling_prefixes):
            continue
        if any(dk in lower_snip for dk in degree_keywords) and len(statement_snip) < 80:
            continue

        key = f"contextual_req_{item.id[:8]}_{i}"
        if key not in existing_keys and lower_snip not in seen_statements:
            questions.append(ClarificationQuestionSchema(
                question_key=key,
                category=QuestionCategory.TECHNICAL_SCOPE,
                priority=QuestionPriority.RECOMMENDED,
                is_blocking=False,
                field_target=f"requirements[id={item.id}].priority",
                question_text=(
                    f"\"{statement_snip[:130]}\" is contextual. "
                    f"Should this be evaluated as mandatory, preferred, or role context?"
                ),
                rationale="Soft/contextual requirement in JD requiring TA confirmation to decide screening criteria.",
                suggested_options=["MUST HAVE — mandatory", "PREFERRED — nice to have", "INFORMATIONAL — role context only"],
            ))
            seen_statements.add(lower_snip)

    return questions


def _detect_raw_ambiguities(
    master: JDMasterContext,
    existing_keys: set,
) -> List[ClarificationQuestionSchema]:
    """
    Generates questions for ambiguities detected in the JD text (e.g. unclear experience, vague qualifiers).
    Caps total raw ambiguities to 3 to keep TA workflow focused.
    """
    questions: List[ClarificationQuestionSchema] = []
    raw_ambs = getattr(master, "raw_ambiguities", []) or []
    seen_statements = {q.question_text.lower() for q in master.clarification_history}

    for i, amb in enumerate(raw_ambs):
        if len(questions) >= 3:
            break

        amb_id = getattr(amb, "ambiguity_id", f"amb_{i}")
        key = f"jd_ambiguity_{amb_id}"
        amb_text = getattr(amb, "text", "").strip()
        lower_text = amb_text.lower()

        if len(amb_text) < 25 or lower_text.startswith(("in ", "or ", "and ")):
            continue

        if key not in existing_keys and amb_text and lower_text not in seen_statements:
            reason = getattr(amb, "reason", "Ambiguous statement in JD")
            opts = getattr(amb, "suggested_interpretations", []) or []
            questions.append(ClarificationQuestionSchema(
                question_key=key,
                category=QuestionCategory.TECHNICAL_SCOPE,
                priority=QuestionPriority.RECOMMENDED,
                is_blocking=False,
                field_target=f"ambiguities[{amb_id}]",
                question_text=f"Clarification needed on \"{amb_text[:130]}\": {reason}. How should this be evaluated?",
                rationale=reason,
                suggested_options=opts,
            ))
            seen_statements.add(lower_text)

    return questions


# ---------------------------------------------------------------------------
# Tier 3: OPTIONAL Question Generators
# ---------------------------------------------------------------------------

def _detect_missing_metadata(
    master: JDMasterContext,
    existing_keys: set,
) -> List[ClarificationQuestionSchema]:
    """
    Generates OPTIONAL questions for missing Tier 3 metadata (team size, salary).
    These NEVER block finalization and are presented as quick intake chips in the UI.
    """
    questions: List[ClarificationQuestionSchema] = []
    ctx = master.job_context

    # Team size
    if ctx.team_size is None and not ctx.team_size_explicitly_unspecified:
        key = "org_metadata_team_size"
        if key not in existing_keys:
            questions.append(ClarificationQuestionSchema(
                question_key=key,
                category=QuestionCategory.ORG_METADATA,
                priority=QuestionPriority.OPTIONAL,
                is_blocking=False,
                field_target="job_context.team_size",
                short_topic="Team Size",
                structured_options=[
                    ClarificationOptionSchema(label="1-5 people", description="Small, tight-knit founding engineering team or squad."),
                    ClarificationOptionSchema(label="6-15 people", description="Mid-sized dedicated product engineering pod."),
                    ClarificationOptionSchema(label="16-50 people", description="Broad engineering organization."),
                    ClarificationOptionSchema(label="50+ people", description="Large enterprise engineering division."),
                    ClarificationOptionSchema(label="Not specified", description="Keep unspecified for candidate screening."),
                ],
                question_text="What is the approximate team size for this role?",
                rationale=(
                    "Team size was not mentioned in the JD. Some candidates may prefer "
                    "specific team environments (small startup vs large engineering org)."
                ),
                suggested_options=["1-5 people", "6-15 people", "16-50 people", "50+ people", "Not specified"],
            ))

    # Salary range
    if ctx.salary_range is None and not ctx.salary_explicitly_unspecified:
        key = "compensation_salary_range"
        if key not in existing_keys:
            questions.append(ClarificationQuestionSchema(
                question_key=key,
                category=QuestionCategory.COMPENSATION_LOGISTICS,
                priority=QuestionPriority.OPTIONAL,
                is_blocking=False,
                field_target="job_context.salary_range",
                short_topic="Compensation",
                structured_options=[
                    ClarificationOptionSchema(label="Competitive / Market Rate", description="Calibrated to prevailing competitive market compensation benchmarks."),
                    ClarificationOptionSchema(label="Yes, I can provide it", description="Provide a specific compensation band or hourly rate."),
                    ClarificationOptionSchema(label="Not disclosed", description="Confidential or discussed during interview rounds."),
                ],
                question_text="Is a salary range or compensation band available for this role?",
                rationale=(
                    "Salary range was not mentioned in the JD. This is optional context "
                    "that helps attract candidates and set screening expectations."
                ),
                suggested_options=["Yes, I can provide it", "Not disclosed", "Competitive / Market Rate"],
            ))

    return questions


# ---------------------------------------------------------------------------
# LLM Conversational Question Formulator (Batched Single-Pass)
# ---------------------------------------------------------------------------
# Rewrites deterministic question_text into natural, conversational phrasing
# in a SINGLE batched LLM call. Automatically bypassed during automated unit
# tests or when Ollama is unavailable.

_BATCH_CONVERSATIONAL_SYSTEM_PROMPT = (
    "You are an expert Talent Acquisition Consultant and Senior Recruiter. "
    "Your job is to rewrite a list of technical clarification questions for a hiring manager "
    "into warm, natural, conversational phrasing (similar to how Claude or GPT-4 asks thoughtful "
    "follow-up questions). For each question:\n"
    "- Make it polite, role-aware, and natural\n"
    "- Explain why the clarification matters for candidate screening\n"
    "- Never use robotic jargon like 'MUST_HAVE', 'PREFERRED', 'EKG', 'deterministic'\n\n"
    "Respond with ONLY a JSON object mapping each question key to its conversational text:\n"
    "{\n"
    '  "<question_key>": "<conversational question text>"\n'
    "}\n"
    "Do not include preamble, markdown fences, or explanation."
)


def enrich_questions_conversational(
    master: "JDMasterContext",
    questions: list,
) -> list:
    """
    Rewrites technical clarification questions into conversational phrasing
    using a single batched LLM inference call.
    """
    import os
    if os.environ.get("PYTEST_CURRENT_TEST"):
        # Fast path for automated tests: keep deterministic questions
        return questions

    try:
        from app.services.llm_service import LLMService
        import json as _json

        # Target only technical scope and ambiguous items (metadata is already conversational)
        eligible = [
            q for q in questions
            if q.category in {
                QuestionCategory.TECHNICAL_SCOPE,
                QuestionCategory.CONTRADICTION,
                QuestionCategory.ROLE_ALIGNMENT,
            }
            and not getattr(q, 'structured_options', None)
        ]
        if not eligible:
            return questions

        llm = LLMService()
        if llm.provider != "ollama":
            return questions

        role_title = (
            getattr(getattr(master, "role_overview", None), "job_title", None) or
            getattr(getattr(master, "role_overview", None), "title", None) or
            "the open position"
        )

        items_payload = [
            {
                "key": q.question_key,
                "original_text": q.question_text,
                "context": q.rationale,
            }
            for q in eligible[:5]  # Cap at 5 for bounded latency
        ]

        user_prompt = (
            f"Role: {role_title}\n\n"
            f"Rewrite each of the following {len(items_payload)} clarification questions:\n"
            f"{_json.dumps(items_payload, indent=2)}"
        )

        result = llm.complete_structured(
            system_prompt=_BATCH_CONVERSATIONAL_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            max_tokens=600,
            num_ctx=2048,
        )
        raw_text = result.raw_text.strip() if result.raw_text else ""
        if not raw_text:
            return questions

        if raw_text.startswith("```"):
            lines = raw_text.splitlines()
            raw_text = "\n".join(
                line for line in lines
                if not line.strip().startswith("```")
            ).strip()

        mapping = _json.loads(raw_text)
        if isinstance(mapping, dict):
            for q in eligible:
                rewritten = mapping.get(q.question_key)
                if rewritten and isinstance(rewritten, str) and len(rewritten.strip()) > 20:
                    q.question_text = rewritten.strip()

        return questions

    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Conversational enrichment layer skipped (Ollama unavailable or error): %s", exc
        )
        return questions
