"""
Seed data for Enterprise Knowledge Graph.

This module contains reviewed, provenance-aware seed entities for the EKG.
All entities have stable IDs, canonical names, aliases, and documented sources.

Design principles:
- Reviewed and defensible technical relationships only
- No invented associations
- Careful distinction between similar terms (C vs C++, Verilog vs SystemVerilog)
- Reuse and normalize from existing RAG taxonomies where appropriate
"""
from typing import List, Tuple

from app.schemas.master_context import EKGEntity, EKGEntityType


def get_seed_entities() -> List[EKGEntity]:
    """
    Return reviewed seed entities for EKG initialization.
    
    Source: Manual curation aligned with existing RAG knowledge base.
    """
    return [
        # ========== PROGRAMMING LANGUAGES ==========
        EKGEntity(
            entity_id="lang_python",
            name="Python",
            entity_type=EKGEntityType.LANGUAGE,
            aliases=["python", "py", "python3", "python 3"],
            source="seed_data_v1",
            confidence=1.0
        ),
        EKGEntity(
            entity_id="lang_java",
            name="Java",
            entity_type=EKGEntityType.LANGUAGE,
            aliases=["java"],
            source="seed_data_v1",
            confidence=1.0
        ),
        EKGEntity(
            entity_id="lang_javascript",
            name="JavaScript",
            entity_type=EKGEntityType.LANGUAGE,
            aliases=["javascript", "js", "ecmascript"],
            source="seed_data_v1",
            confidence=1.0
        ),
        EKGEntity(
            entity_id="lang_typescript",
            name="TypeScript",
            entity_type=EKGEntityType.LANGUAGE,
            aliases=["typescript", "ts"],
            source="seed_data_v1",
            confidence=1.0
        ),
        EKGEntity(
            entity_id="lang_c",
            name="C",
            entity_type=EKGEntityType.LANGUAGE,
            aliases=["c", "ansi c", "c programming"],
            source="seed_data_v1",
            confidence=1.0
        ),
        EKGEntity(
            entity_id="lang_cpp",
            name="C++",
            entity_type=EKGEntityType.LANGUAGE,
            aliases=["c++", "cpp", "c plus plus", "cplusplus"],
            source="seed_data_v1",
            confidence=1.0
        ),
        EKGEntity(
            entity_id="lang_csharp",
            name="C#",
            entity_type=EKGEntityType.LANGUAGE,
            aliases=["c#", "csharp", "c sharp"],
            source="seed_data_v1",
            confidence=1.0
        ),
        EKGEntity(
            entity_id="lang_go",
            name="Go",
            entity_type=EKGEntityType.LANGUAGE,
            aliases=["go", "golang"],
            source="seed_data_v1",
            confidence=1.0
        ),
        EKGEntity(
            entity_id="lang_rust",
            name="Rust",
            entity_type=EKGEntityType.LANGUAGE,
            aliases=["rust"],
            source="seed_data_v1",
            confidence=1.0
        ),
        
        # Hardware/Embedded Languages
        EKGEntity(
            entity_id="lang_vhdl",
            name="VHDL",
            entity_type=EKGEntityType.LANGUAGE,
            aliases=["vhdl"],
            source="seed_data_v1",
            confidence=1.0
        ),
        EKGEntity(
            entity_id="lang_verilog",
            name="Verilog",
            entity_type=EKGEntityType.LANGUAGE,
            aliases=["verilog"],
            source="seed_data_v1",
            confidence=1.0
        ),
        EKGEntity(
            entity_id="lang_systemverilog",
            name="SystemVerilog",
            entity_type=EKGEntityType.LANGUAGE,
            aliases=["systemverilog", "system verilog"],
            source="seed_data_v1",
            confidence=1.0
        ),
        
        # ========== WEB FRAMEWORKS ==========
        EKGEntity(
            entity_id="fw_react",
            name="React",
            entity_type=EKGEntityType.FRAMEWORK,
            aliases=["react", "reactjs", "react.js"],
            source="seed_data_v1",
            confidence=1.0
        ),
        EKGEntity(
            entity_id="fw_angular",
            name="Angular",
            entity_type=EKGEntityType.FRAMEWORK,
            aliases=["angular", "angularjs"],
            source="seed_data_v1",
            confidence=1.0
        ),
        EKGEntity(
            entity_id="fw_vue",
            name="Vue",
            entity_type=EKGEntityType.FRAMEWORK,
            aliases=["vue", "vuejs", "vue.js"],
            source="seed_data_v1",
            confidence=1.0
        ),
        
        # Backend Frameworks
        EKGEntity(
            entity_id="fw_django",
            name="Django",
            entity_type=EKGEntityType.FRAMEWORK,
            aliases=["django"],
            source="seed_data_v1",
            confidence=1.0
        ),
        EKGEntity(
            entity_id="fw_flask",
            name="Flask",
            entity_type=EKGEntityType.FRAMEWORK,
            aliases=["flask"],
            source="seed_data_v1",
            confidence=1.0
        ),
        EKGEntity(
            entity_id="fw_fastapi",
            name="FastAPI",
            entity_type=EKGEntityType.FRAMEWORK,
            aliases=["fastapi", "fast api"],
            source="seed_data_v1",
            confidence=1.0
        ),
        EKGEntity(
            entity_id="fw_spring",
            name="Spring",
            entity_type=EKGEntityType.FRAMEWORK,
            aliases=["spring", "spring framework", "spring boot"],
            source="seed_data_v1",
            confidence=1.0
        ),
        EKGEntity(
            entity_id="fw_nodejs",
            name="Node.js",
            entity_type=EKGEntityType.FRAMEWORK,
            aliases=["node", "nodejs", "node.js"],
            source="seed_data_v1",
            confidence=1.0
        ),
        
        # Embedded Frameworks
        EKGEntity(
            entity_id="fw_freertos",
            name="FreeRTOS",
            entity_type=EKGEntityType.FRAMEWORK,
            aliases=["freertos", "free rtos"],
            source="seed_data_v1",
            confidence=1.0
        ),
        
        # ========== TOOLS ==========
        # Version Control
        EKGEntity(
            entity_id="tool_git",
            name="Git",
            entity_type=EKGEntityType.TOOL,
            aliases=["git"],
            source="seed_data_v1",
            confidence=1.0
        ),
        
        # Containers & Orchestration
        EKGEntity(
            entity_id="tool_docker",
            name="Docker",
            entity_type=EKGEntityType.TOOL,
            aliases=["docker"],
            source="seed_data_v1",
            confidence=1.0
        ),
        EKGEntity(
            entity_id="tool_kubernetes",
            name="Kubernetes",
            entity_type=EKGEntityType.TOOL,
            aliases=["kubernetes", "k8s"],
            source="seed_data_v1",
            confidence=1.0
        ),
        
        # Hardware/Embedded Tools
        EKGEntity(
            entity_id="tool_altium",
            name="Altium Designer",
            entity_type=EKGEntityType.TOOL,
            aliases=["altium designer", "altium"],
            source="seed_data_v1",
            confidence=1.0
        ),
        EKGEntity(
            entity_id="tool_matlab",
            name="MATLAB",
            entity_type=EKGEntityType.TOOL,
            aliases=["matlab"],
            source="seed_data_v1",
            confidence=1.0
        ),
        EKGEntity(
            entity_id="tool_simulink",
            name="Simulink",
            entity_type=EKGEntityType.TOOL,
            aliases=["simulink"],
            source="seed_data_v1",
            confidence=1.0
        ),
        EKGEntity(
            entity_id="tool_labview",
            name="LabVIEW",
            entity_type=EKGEntityType.TOOL,
            aliases=["labview", "lab view"],
            source="seed_data_v1",
            confidence=1.0
        ),
        
        # ========== SKILLS ==========
        # Embedded/Hardware Skills
        EKGEntity(
            entity_id="skill_fpga",
            name="FPGA Programming",
            entity_type=EKGEntityType.SKILL,
            aliases=["fpga", "fpga programming", "field programmable gate array"],
            source="seed_data_v1",
            confidence=1.0
        ),
        EKGEntity(
            entity_id="skill_pcb_design",
            name="PCB Design",
            entity_type=EKGEntityType.SKILL,
            aliases=["pcb design", "pcb", "printed circuit board", "circuit board design"],
            source="seed_data_v1",
            confidence=1.0
        ),
        EKGEntity(
            entity_id="skill_jtag",
            name="JTAG Debugging",
            entity_type=EKGEntityType.SKILL,
            aliases=["jtag", "jtag debugging"],
            source="seed_data_v1",
            confidence=1.0
        ),
        EKGEntity(
            entity_id="skill_embedded",
            name="Embedded Systems",
            entity_type=EKGEntityType.SKILL,
            aliases=["embedded systems", "embedded", "embedded development"],
            source="seed_data_v1",
            confidence=1.0
        ),
        EKGEntity(
            entity_id="skill_firmware",
            name="Firmware Development",
            entity_type=EKGEntityType.SKILL,
            aliases=["firmware", "firmware development"],
            source="seed_data_v1",
            confidence=1.0
        ),
        EKGEntity(
            entity_id="skill_arm_cortex",
            name="ARM Cortex-M",
            entity_type=EKGEntityType.SKILL,
            aliases=["arm cortex", "arm cortex-m", "arm cortex m", "cortex-m", "cortex m"],
            source="seed_data_v1",
            confidence=1.0
        ),
        
        # ========== DOMAINS ==========
        EKGEntity(
            entity_id="domain_embedded",
            name="Embedded Systems Engineering",
            entity_type=EKGEntityType.DOMAIN,
            aliases=["embedded systems", "embedded engineering"],
            source="seed_data_v1",
            confidence=1.0
        ),
        EKGEntity(
            entity_id="domain_hardware",
            name="Hardware Engineering",
            entity_type=EKGEntityType.DOMAIN,
            aliases=["hardware engineering", "hardware development"],
            source="seed_data_v1",
            confidence=1.0
        ),
        EKGEntity(
            entity_id="domain_web",
            name="Web Development",
            entity_type=EKGEntityType.DOMAIN,
            aliases=["web development", "web dev"],
            source="seed_data_v1",
            confidence=1.0
        ),
        EKGEntity(
            entity_id="domain_backend",
            name="Backend Development",
            entity_type=EKGEntityType.DOMAIN,
            aliases=["backend", "backend development", "server-side"],
            source="seed_data_v1",
            confidence=1.0
        ),
        EKGEntity(
            entity_id="domain_frontend",
            name="Frontend Development",
            entity_type=EKGEntityType.DOMAIN,
            aliases=["frontend", "frontend development", "front-end", "client-side"],
            source="seed_data_v1",
            confidence=1.0
        ),
        
        # ========== ROLES ==========
        EKGEntity(
            entity_id="role_embedded_engineer",
            name="Embedded Systems Engineer",
            entity_type=EKGEntityType.ROLE,
            aliases=["embedded engineer", "embedded systems engineer", "embedded software engineer"],
            source="seed_data_v1",
            confidence=1.0
        ),
        EKGEntity(
            entity_id="role_backend_engineer",
            name="Backend Engineer",
            entity_type=EKGEntityType.ROLE,
            aliases=["backend engineer", "backend developer", "server engineer"],
            source="seed_data_v1",
            confidence=1.0
        ),
        EKGEntity(
            entity_id="role_frontend_engineer",
            name="Frontend Engineer",
            entity_type=EKGEntityType.ROLE,
            aliases=["frontend engineer", "frontend developer", "front-end engineer"],
            source="seed_data_v1",
            confidence=1.0
        ),
        EKGEntity(
            entity_id="role_fullstack_engineer",
            name="Full Stack Engineer",
            entity_type=EKGEntityType.ROLE,
            aliases=["full stack engineer", "fullstack engineer", "full-stack engineer"],
            source="seed_data_v1",
            confidence=1.0
        ),
    ]


def get_seed_relationships() -> List[Tuple[str, str, str, dict]]:
    """
    Return reviewed seed relationships for EKG initialization.
    
    Returns:
        List of (from_id, to_id, relation_type, attributes) tuples
    
    Relation types:
        - used_in: Language/framework used in another framework/domain
        - belongs_to: Skill belongs to a domain
        - enables: Tool enables a skill
        - required_for: Prerequisite relationship
        - works_in: Role works in a domain
    
    Note: These relationships are documented facts, NOT inferences.
    They do NOT imply that a skill is mandatory for a domain.
    """
    return [
        # Language → Framework relationships
        ("lang_python", "fw_django", "used_in", {"source": "framework_docs"}),
        ("lang_python", "fw_flask", "used_in", {"source": "framework_docs"}),
        ("lang_python", "fw_fastapi", "used_in", {"source": "framework_docs"}),
        ("lang_javascript", "fw_react", "used_in", {"source": "framework_docs"}),
        ("lang_typescript", "fw_react", "used_in", {"source": "framework_docs"}),
        ("lang_javascript", "fw_angular", "used_in", {"source": "framework_docs"}),
        ("lang_typescript", "fw_angular", "used_in", {"source": "framework_docs"}),
        ("lang_javascript", "fw_vue", "used_in", {"source": "framework_docs"}),
        ("lang_javascript", "fw_nodejs", "used_in", {"source": "framework_docs"}),
        ("lang_typescript", "fw_nodejs", "used_in", {"source": "framework_docs"}),
        ("lang_java", "fw_spring", "used_in", {"source": "framework_docs"}),
        ("lang_c", "fw_freertos", "used_in", {"source": "framework_docs"}),
        ("lang_cpp", "fw_freertos", "used_in", {"source": "framework_docs"}),
        
        # Skill → Domain relationships
        ("skill_embedded", "domain_embedded", "belongs_to", {"source": "domain_classification"}),
        ("skill_firmware", "domain_embedded", "belongs_to", {"source": "domain_classification"}),
        ("skill_fpga", "domain_hardware", "belongs_to", {"source": "domain_classification"}),
        ("skill_pcb_design", "domain_hardware", "belongs_to", {"source": "domain_classification"}),
        ("skill_jtag", "domain_hardware", "belongs_to", {"source": "domain_classification"}),
        ("skill_arm_cortex", "domain_embedded", "belongs_to", {"source": "domain_classification"}),
        
        # Tool → Skill relationships
        ("tool_altium", "skill_pcb_design", "enables", {"source": "tool_purpose"}),
        ("tool_matlab", "skill_embedded", "enables", {"source": "tool_purpose"}),
        ("tool_simulink", "skill_embedded", "enables", {"source": "tool_purpose"}),
        ("tool_labview", "skill_embedded", "enables", {"source": "tool_purpose"}),
        
        # Language → Skill relationships (documented requirements, not inferences)
        ("lang_c", "skill_embedded", "required_for", {"source": "industry_standard"}),
        ("lang_cpp", "skill_embedded", "required_for", {"source": "industry_standard"}),
        ("lang_vhdl", "skill_fpga", "required_for", {"source": "industry_standard"}),
        ("lang_verilog", "skill_fpga", "required_for", {"source": "industry_standard"}),
        ("lang_systemverilog", "skill_fpga", "required_for", {"source": "industry_standard"}),
        
        # Role → Domain relationships
        ("role_embedded_engineer", "domain_embedded", "works_in", {"source": "role_definition"}),
        ("role_backend_engineer", "domain_backend", "works_in", {"source": "role_definition"}),
        ("role_frontend_engineer", "domain_frontend", "works_in", {"source": "role_definition"}),
        
        # Framework → Domain relationships
        ("fw_react", "domain_frontend", "belongs_to", {"source": "framework_classification"}),
        ("fw_angular", "domain_frontend", "belongs_to", {"source": "framework_classification"}),
        ("fw_vue", "domain_frontend", "belongs_to", {"source": "framework_classification"}),
        ("fw_django", "domain_backend", "belongs_to", {"source": "framework_classification"}),
        ("fw_flask", "domain_backend", "belongs_to", {"source": "framework_classification"}),
        ("fw_fastapi", "domain_backend", "belongs_to", {"source": "framework_classification"}),
        ("fw_spring", "domain_backend", "belongs_to", {"source": "framework_classification"}),
        ("fw_nodejs", "domain_backend", "belongs_to", {"source": "framework_classification"}),
    ]
