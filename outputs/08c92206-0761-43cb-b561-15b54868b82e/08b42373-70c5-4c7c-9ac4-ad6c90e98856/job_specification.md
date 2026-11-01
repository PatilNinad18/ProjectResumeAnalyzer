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
> - **Concept Summary:** 10-15+ years in semiconductor/system engineering for complex hardware-software co-design and production-scale system integration.
> - **Strong Candidate Signals:** Led large-scale chip design teams for 5+ years; Architected systems with 100M+ transistors; Managed production of 100+ million devices
> - **Weak / Ambiguous Signals:** Mentioned 'semiconductor experience' without specifics; Listed years without hardware ownership context
> - **Screening Question:** Can you describe a system you designed that handled 100M+ transistors at production scale?

### Strong C++ and SystemC/TLM.
> **[AI Guidance — Evaluator Aid]**
> - **Concept Summary:** C++ for low-level system programming and SystemC/TLM for hardware-software co-simulation.
> - **Strong Candidate Signals:** Built real-time simulation models with SystemC/TLM; Optimized C++ code for 100+ Gbps data paths; Used SystemC for hardware verification in production
> - **Weak / Ambiguous Signals:** Mentioned C++ without performance context; SystemC experience limited to tutorials or academic projects
> - **Screening Question:** How did you optimize C++ code for high-speed data paths in your last role?

### Synopsys Virtualizer / VDK experience.
> **[AI Guidance — Evaluator Aid]**
> - **Concept Summary:** Synopsys Virtualizer/VDK for hardware-software co-simulation and early validation.
> - **Strong Candidate Signals:** Deployed Virtualizer for 100+ chip designs; Integrated VDK with production test suites; Reduced simulation time by 40%+ in live projects
> - **Weak / Ambiguous Signals:** Mentioned Virtualizer without metrics; Used VDK only in non-production environments
> - **Screening Question:** How did you measure the impact of Virtualizer on your production timeline?

### SoC/system architecture and virtual prototyping.
> **[AI Guidance — Evaluator Aid]**
> - **Concept Summary:** SoC architecture designs integrated hardware-software stacks for efficient chip-level computing.
> - **Strong Candidate Signals:** Designed custom SoC prototypes using Vivado or Synopsys tools; Published SoC simulation results with 95%+ accuracy in production environments
> - **Weak / Ambiguous Signals:** Mentioned SoC in academic papers without implementation details; Listed SoC as a skill without practical experience
> - **Screening Question:** Have you prototyped an SoC for real-world hardware constraints?

### PCIe / CXL / UCIe / AMBA.
> **[AI Guidance — Evaluator Aid]**
> - **Concept Summary:** PCIe/CXL/UCIe/AMBA are interconnect standards enabling high-speed data transfer between chips and systems.
> - **Strong Candidate Signals:** Implemented PCIe 5.0 or CXL 2.0 in production systems; Optimized UCIe for low-latency memory access in embedded systems
> - **Weak / Ambiguous Signals:** Listed PCIe/CXL without specific version numbers; Referenced AMBA in tutorials without system-level implementation
> - **Screening Question:** Which interconnect standard have you scaled to 100+ concurrent devices?

### Strong understanding of AI/HPC infrastructure.
> **[AI Guidance — Evaluator Aid]**
> - **Concept Summary:** AI/HPC infrastructure supports large-scale machine learning workloads through distributed computing frameworks.
> - **Strong Candidate Signals:** Deployed 100+ GPU clusters for training with <5% latency overhead; Optimized TensorFlow/PyTorch pipelines for 1M+ inference requests/sec
> - **Weak / Ambiguous Signals:** Mentioned AI/HPC in job titles without infrastructure ownership; Used cloud-based AI services without custom infrastructure
> - **Screening Question:** How did you scale AI workloads beyond cloud providers?

### Experience working with both RTL and software teams.
> **[AI Guidance — Evaluator Aid]**
> - **Concept Summary:** Collaborating with hardware teams to design and implement physical circuits while ensuring software integrates seamlessly.
> - **Strong Candidate Signals:** Led RTL-to-software handoff for a production IoT device; Coordinated cross-functional sprints between hardware and software teams
> - **Weak / Ambiguous Signals:** Mentioned 'RTL and software collaboration' without context; Listed as a generic team interaction skill
> - **Screening Question:** Describe a time you resolved a conflict between RTL and software teams during product delivery.

### Chiplet architecture and HBM.
> **[AI Guidance — Evaluator Aid]**
> - **Concept Summary:** Chiplet architecture uses modular, interconnected dies to scale performance while reducing power and cost.
> - **Strong Candidate Signals:** Production chiplets with HBM2E memory interfaces; Multi-die thermal management solutions for high-density packaging
> - **Weak / Ambiguous Signals:** Tutorial-level chiplet designs without real-world deployment
> - **Screening Question:** Describe a production system where you managed HBM memory bandwidth constraints across chiplets.

### AI accelerator/XPU architecture.
> **[AI Guidance — Evaluator Aid]**
> - **Concept Summary:** AI accelerators (XPU) are specialized hardware for high-throughput AI workloads with low latency and energy efficiency.
> - **Strong Candidate Signals:** Custom XPU designs for inference pipelines with 100+ TFLOPS; End-to-end AI model deployment on edge devices with <50ms latency
> - **Weak / Ambiguous Signals:** Generic mentions of 'AI accelerators' without specific metrics or ownership
> - **Screening Question:** How did you optimize an XPU for a real-world AI inference task?

### Emulation platforms such as ZeBu / Palladium / Veloce.
> **[AI Guidance — Evaluator Aid]**
> - **Concept Summary:** Emulation platforms like ZeBu simulate hardware for chip testing without physical devices.
> - **Strong Candidate Signals:** Built production-grade emulation workflows using ZeBu for ASIC validation; Integrated emulation with CI/CD pipelines for automated chip testing
> - **Weak / Ambiguous Signals:** Mentioned emulation tools without specific implementation details; Used emulation in academic projects without production impact
> - **Screening Question:** How did you scale ZeBu/Veloce to handle 100+ concurrent chip test cases?

### Python automation.
> **[AI Guidance — Evaluator Aid]**
> - **Concept Summary:** Python automation enables efficient, reusable workflows for repetitive testing tasks in hardware validation.
> - **Strong Candidate Signals:** Automated 500+ test cases per day using Python in production environments; Maintained Python scripts with 95%+ test coverage across multiple platforms
> - **Weak / Ambiguous Signals:** Used Python for simple scripts without integration into testing pipelines; Tried basic automation in personal projects without real-world impact
> - **Screening Question:** Can you share a Python automation that reduced test cycle time by 30%+?

### B.E. / B.Tech / M.E. / M.Tech / M.S. in Electronics, Electrical, Computer Engineering, or related discipline.
> **[AI Guidance — Evaluator Aid]**
> - **Concept Summary:** Formal engineering degree in electronics, electrical, or computer engineering disciplines.
> - **Strong Candidate Signals:** M.S. in Computer Engineering with thesis on embedded systems; B.Tech in Electronics with industry projects in hardware design
> - **Weak / Ambiguous Signals:** Degree in unrelated field with no engineering focus; Self-study courses without academic credentials
> - **Screening Question:** What specific engineering coursework or projects demonstrate your discipline relevance?

### Demonstrated ownership of a virtual platform / VDK architecture used across multiple products or customer configurations.
> **[AI Guidance — Evaluator Aid]**
> - **Concept Summary:** Building scalable virtual platforms that support multiple product configurations in production environments.
> - **Strong Candidate Signals:** Deployed VDK for 10+ product variants with <5% config drift; Reduced deployment time from hours to minutes via VDK automation
> - **Weak / Ambiguous Signals:** Virtual platform as a concept without production metrics; Tutorial-level VDK implementation without ownership
> - **Screening Question:** Walk me through how you managed VDK for multiple product configurations.

### Experience defining platform architecture spanning compute, connectivity, memory, power, and I/O.
> **[AI Guidance — Evaluator Aid]**
> - **Concept Summary:** Designing integrated hardware-software systems where compute resources, network connections, memory hierarchy, power management, and data transfer mechanisms work together seamlessly for high-performance applications.
> - **Strong Candidate Signals:** Designed heterogeneous compute platforms with GPU/FPGA integration; Optimized memory bandwidth via cache hierarchies in production systems; Reduced power consumption by 20%+ through I/O subsystem tuning
> - **Weak / Ambiguous Signals:** Mentioned 'system architecture' without specific hardware components; Listed generic terms like 'scalable infrastructure' without metrics
> - **Screening Question:** Describe a time you optimized memory bandwidth in a production system with concrete metrics.

### Strong systems-thinking and architecture leadership across hardware, software, and verification teams.
> **[AI Guidance — Evaluator Aid]**
> - **Concept Summary:** Leading cross-functional architecture decisions that align hardware, software, and verification teams to deliver cohesive, production-ready systems.
> - **Strong Candidate Signals:** Led architecture reviews for 5+ hardware/software teams with clear ownership; Defined verification scope that reduced integration defects by 30%; Coordinated hardware validation timelines across multiple teams
> - **Weak / Ambiguous Signals:** Claimed 'systems thinking' without specific team coordination examples; Referenced 'cross-functional' without concrete delivery outcomes
> - **Screening Question:** How did you ensure hardware and software teams aligned on architecture decisions?

### Ability to translate customer XPU requirements into a virtual platform architecture.
> **[AI Guidance — Evaluator Aid]**
> - **Concept Summary:** Converting customer-specific hardware accelerators (XPU) into virtualized, software-managed platforms for consistent performance and scalability.
> - **Strong Candidate Signals:** Virtualized XPU resources using containerized frameworks like Kubernetes; Implemented performance benchmarks for customer XPU requirements in production; Scaled virtual platforms to handle 10k+ concurrent XPU requests
> - **Weak / Ambiguous Signals:** Mentioned 'XPU translation' without technical implementation details; Referenced 'virtual platform' without specific hardware abstraction layers
> - **Screening Question:** Walk me through how you mapped a customer's XPU requirements to your virtual architecture.

### Clear technical communication with RTL, software, and performance teams.
> **[AI Guidance — Evaluator Aid]**
> - **Concept Summary:** Clear technical communication ensures cross-functional alignment on hardware-software interfaces and performance metrics.
> - **Strong Candidate Signals:** Documented cross-team specs for RTL-to-software handoffs; Performance metrics shared in real-time during joint debugging sessions
> - **Weak / Ambiguous Signals:** Vague mentions of 'collaboration' without specific teams or metrics
> - **Screening Question:** How have you resolved a conflict between RTL and software teams over timing constraints?

### Prior experience architecting a virtual platform that shipped across more than one customer program.
> **[AI Guidance — Evaluator Aid]**
> - **Concept Summary:** Architecting virtual platforms that shipped across multiple customer programs ensures scalability and reuse of validation assets.
> - **Strong Candidate Signals:** Led virtual platform deployment for 3+ major customer programs with zero defects; Reduced validation time by 40%+ through cross-program platform reuse
> - **Weak / Ambiguous Signals:** Designed virtual platforms for single projects without multi-customer scaling; Used generic templates without customization for production environments
> - **Screening Question:** Describe a virtual platform that handled 2x more customers than your last project.

### Direct exposure to correlating TLM models against RTL/emulation results.
> **[AI Guidance — Evaluator Aid]**
> - **Concept Summary:** Correlating TLM (Transaction Level Modeling) simulations with RTL (Register Transfer Level) code ensures accurate hardware behavior prediction before physical implementation.
> - **Strong Candidate Signals:** Built TLM models for FPGA validation against RTL in Verilog/VHDL; Reduced simulation divergence by 90%+ using TLM-RTL correlation tools; Published TLM-RTL correlation reports with metrics for hardware teams
> - **Weak / Ambiguous Signals:** Mentioned TLM without RTL integration context; Used TLM in academic projects without production validation
> - **Screening Question:** How did you quantify the impact of TLM-RTL correlation on your team's hardware signoff timeline?

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

