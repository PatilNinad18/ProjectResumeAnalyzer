# Job Evaluation Specification

## 1. Role Overview

- **Job Title:** Type: Technical Lead / Architect
- **Seniority:** _unspecified_
- **Location / Work Mode:** Bangalore / Hyderabad (Hybrid) (hybrid)
- **Salary Range:** Not specified in the Job Description

## 2. Requirements

### Must-Have

- 10–15+ years of semiconductor/system engineering experience.
- Strong C++ and SystemC/TLM.
- Synopsys Virtualizer / VDK experience.
- SoC/system architecture and virtual prototyping.
- PCIe / CXL / UCIe / AMBA.
- Strong understanding of AI/HPC infrastructure.
- Experience working with both RTL and software teams.
- B.E. / B.Tech / M.E. / M.Tech / M.S. in Electronics, Electrical, Computer Engineering, or related discipline.
- Demonstrated ownership of a virtual platform / VDK architecture used across multiple products or customer configurations.
- Experience defining platform architecture spanning compute, connectivity, memory, power, and I/O.
- Strong systems-thinking and architecture leadership across hardware, software, and verification teams.
- Ability to translate customer XPU requirements into a virtual platform architecture.
- Clear technical communication with RTL, software, and performance teams.

### Preferred

- Chiplet architecture and HBM.
- AI accelerator/XPU architecture.
- Emulation platforms such as ZeBu / Palladium / Veloce.
- Python automation.
- Prior experience architecting a virtual platform that shipped across more than one customer program.
- Direct exposure to correlating TLM models against RTL/emulation results.

## 3. Responsibilities

- Customer XPU / Chiplet Architecture Analysis: Study customer XPU/SoC architecture, identify software-visible and performance-critical components, define virtualization requirements and model abstraction levels, and identify interfaces between the customer compute die and the company’s chiplets.
- Virtual Platform / VDK Foundation: Architect and establish the Synopsys Virtualizer/VDK environment; develop reusable SystemC/TLM- based platform infrastructure; define platform configuration, component hierarchy, and interconnect architecture; establish reusable VP templates for different customer XPU configurations.
- Multi-Chiplet / Multi-XPU Scalability: Define scalable virtual architectures representing multiple chiplets/XPUs, and support scale-up and multi-device configurations.
- AI Infrastructure System Modelling: Define the complete system-level virtual platform architecture and integrate compute, connectivity, memory, power, and I/O models.
- System Performance & Architecture Exploration: Work with performance architects to enable architecture trade-off studies.
- RTL / VP / Emulation Correlation: Define the methodology for correlating TLM models with RTL and emulation.
- Automated Regression & Performance Infrastructure: Define the overall VP validation and regression strategy.
- Synopsys Virtualizer/VDK-based platform architecture and reusable VP templates.
- System-level virtual platform integrating compute, connectivity, memory, power, and I/O models.
- VP validation/regression strategy and RTL/emulation correlation methodology.

## 4. Evidence & Evaluation Rules

### 10–15+ years of semiconductor/system engineering experience.
> **[AI Guidance — Evaluator Aid]**
> - **Concept Summary:** 10-15+ years of hands-on semiconductor/system engineering experience in real-world production environments.
> - **Strong Candidate Signals:** Designed and validated complex SoC architectures for 3+ major semiconductor products; Led cross-functional teams through full product lifecycle from RTL to tapeout; Published at least 2 IEEE papers on advanced semiconductor design techniques
> - **Weak / Ambiguous Signals:** Mentioned 'semiconductor experience' without specific product cycles or metrics; Listed general engineering skills without production context
> - **Screening Question:** Can you describe a time when you led a team through a full semiconductor product tapeout with specific challenges?

### Strong C++ and SystemC/TLM.
> **[AI Guidance — Evaluator Aid]**
> - **Concept Summary:** Proficiency in C++ for system-level programming and SystemC/TLM for hardware-software co-design.
> - **Strong Candidate Signals:** Built production-grade simulation models using SystemC/TLM for 100M+ transaction throughput; Optimized C++ code for real-time hardware-software co-simulation with <50ms latency; Integrated SystemC/TLM with Verilog for hardware validation in 3+ major projects
> - **Weak / Ambiguous Signals:** Mentioned 'C++ and SystemC' without production metrics or specific use cases; Referenced tutorials or academic projects without real-world deployment
> - **Screening Question:** How did you optimize C++ performance in a production system where latency was critical?

### Synopsys Virtualizer / VDK experience.
> **[AI Guidance — Evaluator Aid]**
> - **Concept Summary:** Experience with Synopsys Virtualizer to accelerate hardware-software co-simulation and reduce validation cycles.
> - **Strong Candidate Signals:** Reduced simulation time by 40%+ using Synopsys Virtualizer for complex SoC validation; Integrated Virtualizer with existing testbenches to validate hardware-software interactions; Deployed Virtualizer in production for at least 2 major semiconductor projects
> - **Weak / Ambiguous Signals:** Mentioned 'Virtualizer experience' without specific metrics or project impact; Referenced virtualization concepts without real-world implementation details
> - **Screening Question:** What specific validation cycle reduction did you achieve with Synopsys Virtualizer?

### SoC/system architecture and virtual prototyping.
> **[AI Guidance — Evaluator Aid]**
> - **Concept Summary:** SoC/system architecture defines hardware integration patterns for complex computing systems, enabling efficient resource sharing and co-design of hardware-software interfaces.
> - **Strong Candidate Signals:** Designed custom SoCs with hardware-software co-verification using UVM; Built virtual prototypes for silicon validation in 5+ hardware iterations; Reduced time-to-market by 30% via system-level simulation
> - **Weak / Ambiguous Signals:** Mentioned 'SoC design' without specific verification methodologies; Referenced virtual prototyping in academic projects only
> - **Screening Question:** How did you reduce hardware iteration cycles when validating a complex SoC design?

### PCIe / CXL / UCIe / AMBA.
> **[AI Guidance — Evaluator Aid]**
> - **Concept Summary:** PCIe/CXL/UCIe/AMBA are high-speed interconnect standards enabling efficient data transfer between processors and memory systems in modern computing.
> - **Strong Candidate Signals:** Implemented PCIe 5.0 with CXL 2.0 for NVMe storage in production systems; Optimized AMBA4 bus traffic using UCIe for low-latency memory access; Reduced interconnect latency by 40% via PCIe/CXL co-design
> - **Weak / Ambiguous Signals:** Listed standards without implementation context; Mentioned 'exposure to' without production metrics
> - **Screening Question:** What specific latency reduction did you achieve using PCIe/CXL in a real system?

### Strong understanding of AI/HPC infrastructure.
> **[AI Guidance — Evaluator Aid]**
> - **Concept Summary:** AI/HPC infrastructure involves scalable hardware and software stacks for large-scale machine learning workloads and high-performance computing applications.
> - **Strong Candidate Signals:** Deployed 100+ GPU clusters with custom data pipelines for AI training; Optimized HPC workloads using NVLink for 5x faster inference; Managed petabyte-scale datasets in production AI systems
> - **Weak / Ambiguous Signals:** Referenced 'AI infrastructure' without specific hardware scale; Mentioned 'familiarity with' without hands-on deployment
> - **Screening Question:** How did you scale AI training across 100+ GPUs while maintaining latency under 50ms?

### Experience working with both RTL and software teams.
> **[AI Guidance — Evaluator Aid]**
> - **Concept Summary:** Collaborating with RTL (hardware) and software teams to integrate chip designs into end-to-end systems.
> - **Strong Candidate Signals:** Led cross-functional integration of hardware and software in silicon validation; Produced debug reports for RTL-software interface issues in production systems
> - **Weak / Ambiguous Signals:** Mentioned 'RTL-software collaboration' without specific projects; Listed teams but no ownership or metrics
> - **Screening Question:** Describe a time you resolved a critical RTL-software integration issue with measurable impact.

### Chiplet architecture and HBM.
> **[AI Guidance — Evaluator Aid]**
> - **Concept Summary:** Chiplet architecture uses modular silicon dies connected via high-bandwidth interconnects for scalable, cost-effective chip designs.
> - **Strong Candidate Signals:** HBM3 memory integration in multi-die systems; Production of 100+ chiplet designs with 20%+ performance gains; Experience with TSMC 5nm or similar node chiplets
> - **Weak / Ambiguous Signals:** Tutorial-level chiplet simulations without real hardware; Mentions of 'chiplet' without HBM or interconnect specifics
> - **Screening Question:** How have you optimized memory bandwidth in a chiplet design with HBM?

### AI accelerator/XPU architecture.
> **[AI Guidance — Evaluator Aid]**
> - **Concept Summary:** AI accelerators (XPU) are specialized hardware for high-throughput AI workloads, balancing latency and energy efficiency.
> - **Strong Candidate Signals:** Production deployment of 100+ inference models on custom XPU; Quantization techniques reducing latency by 30%+ in production; End-to-end pipeline for model training to inference
> - **Weak / Ambiguous Signals:** Academic projects with no production metrics; Generic 'AI accelerator' mentions without hardware specs
> - **Screening Question:** Show me a production metric where your XPU improved AI latency or throughput.

### Emulation platforms such as ZeBu / Palladium / Veloce.
> **[AI Guidance — Evaluator Aid]**
> - **Concept Summary:** Hardware emulation platforms that simulate physical chips for early software testing.
> - **Strong Candidate Signals:** ZeBu or Palladium in production test environments; Customized hardware models for specific SoC validation
> - **Weak / Ambiguous Signals:** Mentioned without context of production use; Tutorial-level emulation projects
> - **Screening Question:** Have you shipped a production test suite using ZeBu or Palladium?

### Python automation.
> **[AI Guidance — Evaluator Aid]**
> - **Concept Summary:** Scripting language for automating hardware-software co-validation workflows.
> - **Strong Candidate Signals:** Python-based test automation frameworks for chip validation; CI/CD pipelines integrating Python test scripts
> - **Weak / Ambiguous Signals:** Generic 'familiar with Python' statements; Academic projects without production metrics
> - **Screening Question:** Can you share a Python automation that reduced validation time by 20%+?

### B.E. / B.Tech / M.E. / M.Tech / M.S. in Electronics, Electrical, Computer Engineering, or related discipline.
> **[AI Guidance — Evaluator Aid]**
> - **Concept Summary:** Formal engineering degree in electronics, electrical, or computer engineering disciplines.
> - **Strong Candidate Signals:** Bachelor's/Master's from accredited engineering programs; Relevant coursework in digital design or system architecture
> - **Weak / Ambiguous Signals:** Generic mentions of 'computer engineering' without specific focus; Self-study certificates without formal degree validation
> - **Screening Question:** Which engineering courses directly supported your work in hardware-software integration?

### Demonstrated ownership of a virtual platform / VDK architecture used across multiple products or customer configurations.
> **[AI Guidance — Evaluator Aid]**
> - **Concept Summary:** Building reusable virtual platform infrastructure that scales across products and customer deployments.
> - **Strong Candidate Signals:** Deployed VDK for 5+ product lines with <5% configuration drift; Reduced platform maintenance costs by 30% through automation
> - **Weak / Ambiguous Signals:** Vague references to 'virtual platforms' without metrics; Tutorial-level VDK implementations without production impact
> - **Screening Question:** Show me a metric where your VDK reduced time-to-market for products.

### Experience defining platform architecture spanning compute, connectivity, memory, power, and I/O.
> **[AI Guidance — Evaluator Aid]**
> - **Concept Summary:** Defining platform architecture covers hardware-software integration for performance, scalability, and reliability in real-world systems.
> - **Strong Candidate Signals:** Designed heterogeneous compute platforms with GPU/CPU co-architecture; Optimized memory bandwidth via custom interconnects for high-throughput workloads; Led power-aware I/O subsystems reducing energy consumption by 20%+ in production
> - **Weak / Ambiguous Signals:** Mentioned 'platform architecture' without hardware specifics; Listed generic components without performance metrics
> - **Screening Question:** Describe a time you reduced latency by optimizing memory access patterns across heterogeneous hardware.

### Strong systems-thinking and architecture leadership across hardware, software, and verification teams.
> **[AI Guidance — Evaluator Aid]**
> - **Concept Summary:** Architectural leadership involves coordinating cross-functional teams to align hardware, software, and verification deliverables for system reliability.
> - **Strong Candidate Signals:** Spearheaded hardware-software co-design reviews with verification teams; Reduced cross-team handoff delays by 30% through standardized interface specifications; Owned end-to-end validation of platform architecture for production deployments
> - **Weak / Ambiguous Signals:** Referenced 'systems thinking' without concrete coordination examples; Used vague terms like 'collaboration' without measurable outcomes
> - **Screening Question:** How did you ensure hardware and software teams aligned on critical path items during a platform release?

### Ability to translate customer XPU requirements into a virtual platform architecture.
> **[AI Guidance — Evaluator Aid]**
> - **Concept Summary:** Translating customer XPU needs into virtual platforms requires mapping hardware capabilities to software abstractions for efficient execution.
> - **Strong Candidate Signals:** Built virtual platforms matching customer XPU specifications with 95%+ accuracy; Implemented runtime profiling to validate XPU utilization in production environments; Documented migration paths from legacy systems to virtualized XPU architectures
> - **Weak / Ambiguous Signals:** Mentioned 'virtual platform' without specifying XPU constraints; Used generic terms like 'translate requirements' without technical validation steps
> - **Screening Question:** Give an example where you adapted a virtual platform to meet specific customer XPU performance targets.

### Clear technical communication with RTL, software, and performance teams.
> **[AI Guidance — Evaluator Aid]**
> - **Concept Summary:** Clear technical communication ensures cross-functional alignment on hardware-software interfaces and performance tradeoffs in chip design.
> - **Strong Candidate Signals:** Documented interface specs for RTL-to-software handoff; Performance metrics from joint debugging sessions; Ownership of cross-team feature delivery timelines
> - **Weak / Ambiguous Signals:** Generic mentions of 'collaboration' without specifics; Passive participation in meetings without ownership
> - **Screening Question:** Describe a time you resolved a critical RTL-software interface conflict with measurable outcomes.

### Prior experience architecting a virtual platform that shipped across more than one customer program.
> **[AI Guidance — Evaluator Aid]**
> - **Concept Summary:** Architecting reusable virtual platforms for multiple customer programs in production.
> - **Strong Candidate Signals:** Virtual platform shipped to 3+ customers with distinct requirements; Cross-program architecture documentation and version control
> - **Weak / Ambiguous Signals:** Single-customer platform with no scalability evidence; Theoretical designs without customer delivery
> - **Screening Question:** Describe a virtual platform that served 2+ customer programs post-shipping.

### Direct exposure to correlating TLM models against RTL/emulation results.
> **[AI Guidance — Evaluator Aid]**
> - **Concept Summary:** Correlating TLM (Transaction Level Modeling) simulations with RTL (Register Transfer Level) code ensures accurate hardware behavior validation before silicon release.
> - **Strong Candidate Signals:** Built TLM models for complex SoC designs using SystemVerilog; Reduced simulation convergence time by 30%+ via TLM-RTL correlation; Published correlation reports with defect resolution metrics
> - **Weak / Ambiguous Signals:** Mentioned TLM in academic projects without implementation; Used generic simulation tools without specific correlation metrics
> - **Screening Question:** How did you quantify accuracy improvements from TLM-RTL correlation in your last production system?

## 5. JD-Specific Evaluation Parameters

_None identified — no JD evidence supported additional parameters._

## 6. Ambiguities & Missing Information

**Ambiguities Requiring TA Clarification**

- **"10–15+ years of semiconductor/system engineering experience."** — Experience range unclear (e.g., "5+ years") _(TA confirmation required)_
- **"Strong understanding of AI/HPC infrastructure."** — Subjective qualifier without objective criteria _(TA confirmation required)_

**Missing Information**

_Absent from JD. Do not fabricate or assume defaults._

- **team_size:** Team size affects culture fit expectations.
  - Action: Ask TA to confirm or mark as not available.
- **salary_range:** Salary range affects candidate expectations and attraction.
  - Action: Ask TA to confirm or mark as not disclosed.

## 7. Evaluation Priorities

1. Prioritize candidates demonstrating hands-on production depth in core technical skills: Strong C++ and SystemC/TLM., Python automation..
2. Evaluate demonstrated ownership of major deliverables: Customer XPU / Chiplet Architecture Analysis: Study customer XPU/SoC architecture, identify software-visible and perform.
3. Differentiate competitive candidates through demonstrated depth in preferred skills: Chiplet architecture and HBM., AI accelerator/XPU architecture., Emulation platforms such as ZeBu / Palladium / Veloce..

## 8. Compliance

_None detected._

