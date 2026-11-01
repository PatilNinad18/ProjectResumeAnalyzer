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
> - **Concept Summary:** Semiconductor/system engineering involves designing and optimizing hardware-software interfaces for complex integrated circuits.
> - **Strong Candidate Signals:** Led production of 100M+ transistor IC designs; Architected custom IP cores for 5nm processes; Managed cross-functional teams in semiconductor fabs
> - **Weak / Ambiguous Signals:** Basic knowledge of semiconductor fabrication; Experience with academic research projects
> - **Screening Question:** Describe a production system you designed that handled >100M transistors.

### Strong C++ and SystemC/TLM.
> **[AI Guidance — Evaluator Aid]**
> - **Concept Summary:** C++ enables high-performance systems programming, while SystemC/TLM provides hardware description for modeling complex systems.
> - **Strong Candidate Signals:** Built production C++ libraries with >10k LOC; Modeled system-level behavior using SystemC TLM; Optimized performance in real-time simulation environments
> - **Weak / Ambiguous Signals:** Learned C++ for academic projects; Used SystemC for small-scale simulations
> - **Screening Question:** Show an example of C++ code that handled >10k lines of production code.

### Synopsys Virtualizer / VDK experience.
> **[AI Guidance — Evaluator Aid]**
> - **Concept Summary:** Synopsys Virtualizer creates virtual test environments for hardware verification, reducing physical prototyping costs.
> - **Strong Candidate Signals:** Deployed Virtualizer for 100+ test cases; Reduced silicon validation time by 30%; Integrated with existing EDA tools like VCS
> - **Weak / Ambiguous Signals:** Used Virtualizer for small-scale testing; Basic familiarity with virtualization concepts
> - **Screening Question:** How did you use Virtualizer to reduce silicon validation time?

### SoC/system architecture and virtual prototyping.
> **[AI Guidance — Evaluator Aid]**
> - **Concept Summary:** Designing chip-level systems using simulation to validate hardware before physical production.
> - **Strong Candidate Signals:** Led virtual prototyping for PCIe 4.0 SoC designs with Cadence Xcelium; Reduced silicon risk by 30% via early-stage SoC validation; Published IEEE papers on virtual prototyping for ARM-based systems
> - **Weak / Ambiguous Signals:** Mentioned 'virtual prototyping' without specific tools or metrics; Used simulation for academic projects only
> - **Screening Question:** How did you reduce silicon risk using virtual prototyping in a production environment?

### PCIe / CXL / UCIe / AMBA.
> **[AI Guidance — Evaluator Aid]**
> - **Concept Summary:** High-speed interconnect standards enabling direct memory access between chips.
> - **Strong Candidate Signals:** Deployed CXL 2.0 for NVMe over Fabric in production systems; Optimized PCIe 5.0 bandwidth for AI accelerators with 40% latency reduction; Implemented UCIe for secure interconnects in hybrid cloud deployments
> - **Weak / Ambiguous Signals:** Listed standards without implementation context; Used PCIe 4.0 in non-production environments
> - **Screening Question:** Can you share a specific example where you improved system performance using PCIe/CXL?

### Strong understanding of AI/HPC infrastructure.
> **[AI Guidance — Evaluator Aid]**
> - **Concept Summary:** Infrastructure for large-scale AI workloads with high compute and memory capacity.
> - **Strong Candidate Signals:** Scaled HPC clusters to 10k+ GPUs for real-time AI inference; Designed memory hierarchy for 500+ node AI systems with 99.99% uptime; Optimized Kubernetes clusters for AI workloads with 40% cost reduction
> - **Weak / Ambiguous Signals:** Mentioned 'AI infrastructure' without specific metrics; Used cloud services for AI workloads without ownership
> - **Screening Question:** How did you handle memory bottlenecks in your largest AI deployment?

### Experience working with both RTL and software teams.
> **[AI Guidance — Evaluator Aid]**
> - **Concept Summary:** Collaborating with RTL (hardware) and software teams to integrate complex semiconductor designs into working systems.
> - **Strong Candidate Signals:** Led cross-functional integration of RTL code with software stacks in production chips; Documented interface specs for hardware-software co-design in 3+ product lines
> - **Weak / Ambiguous Signals:** Mentioned 'collaboration' without specific integration examples; Listed teams without ownership or metrics
> - **Screening Question:** Describe a time you resolved a critical RTL-software interface conflict in production.

### Chiplet architecture and HBM.
> **[AI Guidance — Evaluator Aid]**
> - **Concept Summary:** Designing chiplets with HBM memory to maximize bandwidth and reduce latency for high-performance computing.
> - **Strong Candidate Signals:** HBM3 memory integration in production chips; Chiplet interconnects using CXL or UCIe; Bandwidth optimization metrics
> - **Weak / Ambiguous Signals:** Generic 'chiplet' mentions without implementation; HBM as a buzzword without technical depth
> - **Screening Question:** Describe a chiplet architecture you implemented with HBM memory that improved performance.

### AI accelerator/XPU architecture.
> **[AI Guidance — Evaluator Aid]**
> - **Concept Summary:** Designing specialized hardware accelerators for AI workloads to offload computation from CPUs.
> - **Strong Candidate Signals:** AI accelerator deployment in production systems; Quantization or pruning techniques applied; Throughput metrics for inference tasks
> - **Weak / Ambiguous Signals:** Academic projects without real-world deployment; Vague mentions of 'AI accelerators' without specifics
> - **Screening Question:** What AI accelerator did you deploy that handled real user traffic?

### Emulation platforms such as ZeBu / Palladium / Veloce.
> **[AI Guidance — Evaluator Aid]**
> - **Concept Summary:** Hardware emulation platforms that simulate physical semiconductor behavior for chip validation.
> - **Strong Candidate Signals:** Built ZeBu/Palladium/Veloce-based test harnesses for production silicon; Reduced physical prototyping costs by 40%+ via emulation; Managed 100+ concurrent emulation sessions in production
> - **Weak / Ambiguous Signals:** Mentioned emulation tools without specific metrics; Used emulation for non-production validation only
> - **Screening Question:** How did you scale emulation platforms to handle 100+ concurrent test sessions?

### Python automation.
> **[AI Guidance — Evaluator Aid]**
> - **Concept Summary:** Python scripts that automate repetitive tasks in hardware validation workflows.
> - **Strong Candidate Signals:** Automated 50+ test cases per day using Python frameworks; Reduced manual test setup time by 70% with Python; Integrated Python into CI/CD pipelines for hardware validation
> - **Weak / Ambiguous Signals:** Used Python for basic script automation without production impact; Tutorial-level Python projects without real-world metrics
> - **Screening Question:** What specific Python automation reduced your test cycle time by 50%?

### B.E. / B.Tech / M.E. / M.Tech / M.S. in Electronics, Electrical, Computer Engineering, or related discipline.
> **[AI Guidance — Evaluator Aid]**
> - **Concept Summary:** Formal engineering degree in electronics, electrical, or computer engineering disciplines.
> - **Strong Candidate Signals:** Bachelor's/Master's from accredited engineering programs with relevant coursework; Published academic papers on semiconductor design topics
> - **Weak / Ambiguous Signals:** Generic mentions of 'engineering background' without degree specifics; Self-study claims without formal credentials
> - **Screening Question:** What specific courses or projects in your degree covered semiconductor system design?

### Demonstrated ownership of a virtual platform / VDK architecture used across multiple products or customer configurations.
> **[AI Guidance — Evaluator Aid]**
> - **Concept Summary:** Building reusable virtual platforms that scale across multiple product variants and customer configurations.
> - **Strong Candidate Signals:** Architected VDK for 5+ product lines with 90% reuse rate; Reduced configuration time from weeks to hours via virtual platform
> - **Weak / Ambiguous Signals:** Vague references to 'virtual platforms' without metrics; Single-product implementations without cross-product scaling
> - **Screening Question:** How did your VDK handle configuration changes for 3+ distinct customer variants?

### Experience defining platform architecture spanning compute, connectivity, memory, power, and I/O.
> **[AI Guidance — Evaluator Aid]**
> - **Concept Summary:** Defining integrated hardware-software architecture for compute, memory, and I/O subsystems to optimize performance and power in real-world systems.
> - **Strong Candidate Signals:** Designed custom silicon interconnects for high-bandwidth memory access; Led migration from legacy PCIe to NVLink-based compute clusters; Quantified 20% power reduction via optimized memory hierarchy
> - **Weak / Ambiguous Signals:** Mentioned 'platform architecture' without hardware specifics; Described abstract system design concepts without metrics
> - **Screening Question:** Describe a time you reduced latency by optimizing memory hierarchy across compute and I/O subsystems.

### Strong systems-thinking and architecture leadership across hardware, software, and verification teams.
> **[AI Guidance — Evaluator Aid]**
> - **Concept Summary:** Leading cross-functional hardware-software-verification integration to align technical decisions with business outcomes.
> - **Strong Candidate Signals:** Coordinated 5+ teams to deliver silicon validation before tapeout; Reduced verification cycle time by 30% through shared testbench frameworks; Managed hardware budget allocation across teams with 95% on-time delivery
> - **Weak / Ambiguous Signals:** Listed 'systems thinking' without concrete examples; Referenced 'leadership' without ownership metrics
> - **Screening Question:** How did you resolve a conflict between hardware and software teams during a critical tapeout deadline?

### Ability to translate customer XPU requirements into a virtual platform architecture.
> **[AI Guidance — Evaluator Aid]**
> - **Concept Summary:** Translating customer XPU needs into virtualized test platforms that simulate real-world performance constraints.
> - **Strong Candidate Signals:** Built FPGA-based virtual platforms for 3+ customer XPU use cases; Measured latency and throughput under 100ms response targets; Documented 90% of customer requirements in simulation before physical implementation
> - **Weak / Ambiguous Signals:** Used generic terms like 'virtual platform' without technical depth; Mentioned 'requirements translation' without validation metrics
> - **Screening Question:** Give an example where your virtual platform met customer performance targets under real-world conditions.

### Clear technical communication with RTL, software, and performance teams.
> **[AI Guidance — Evaluator Aid]**
> - **Concept Summary:** Ability to translate complex technical details across hardware and software domains into actionable insights for cross-functional teams.
> - **Strong Candidate Signals:** Documented cross-team design handoffs with RTL and software teams; Performance metrics from co-optimized systems; Technical presentations to stakeholders
> - **Weak / Ambiguous Signals:** Mentions of 'communication' without context; Tutorial-level collaboration examples
> - **Screening Question:** How have you resolved a conflict between RTL and software teams during a critical design phase?

### Prior experience architecting a virtual platform that shipped across more than one customer program.
> **[AI Guidance — Evaluator Aid]**
> - **Concept Summary:** End-to-end virtual platforms that shipped to multiple customers with production readiness.
> - **Strong Candidate Signals:** Architected virtual platform used in 3+ customer programs post-launch; Delivered platform with <0.5% defect rate across programs; Handled 1M+ test cases per day in production
> - **Weak / Ambiguous Signals:** Virtual platforms that only worked in lab environments; Platforms that failed to scale beyond single customer
> - **Screening Question:** How did you ensure your virtual platform met SLAs for 3+ customer programs?

### Direct exposure to correlating TLM models against RTL/emulation results.
> **[AI Guidance — Evaluator Aid]**
> - **Concept Summary:** Correlating TLM models with RTL/emulation results ensures accurate simulation of hardware behavior before physical implementation.
> - **Strong Candidate Signals:** Quantitative correlation metrics like P90 latency differences in emulation vs. TLM; Production-ready TLM models used in chip signoff flows; RTL-to-TLM model mapping for specific IP blocks
> - **Weak / Ambiguous Signals:** Mention of TLM without concrete validation metrics; Tutorial-level TLM implementation examples
> - **Screening Question:** Have you quantitatively correlated TLM models with RTL/emulation results in a production chip signoff?

## 5. JD-Specific Evaluation Parameters

_None identified — no JD evidence supported additional parameters._

## 6. Ambiguities & Missing Information

**Resolved Clarifications (TA Confirmed)**

- **"10–15+ years of semiconductor/system engineering experience."** — TA Resolution: contextual

**Ambiguities Requiring TA Clarification**

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

