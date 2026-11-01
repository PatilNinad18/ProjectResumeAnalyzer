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
> - **Concept Summary:** 10-15+ years of hands-on semiconductor/system engineering experience in production environments.
> - **Strong Candidate Signals:** Synthesized 100M+ transistor-level designs for silicon fabrication; Led chip signoff for 3+ 7nm+ process nodes; Managed cross-functional teams through full silicon tapeout cycles
> - **Weak / Ambiguous Signals:** Mentioned 'semiconductor engineering' without specific process nodes; Listed general 'system experience' without production metrics
> - **Screening Question:** Can you describe a chip signoff for 7nm+ process where you directly owned the silicon tapeout?

### Strong C++ and SystemC/TLM.
> **[AI Guidance — Evaluator Aid]**
> - **Concept Summary:** Proficiency in C++ for low-level system programming and SystemC/TLM for hardware modeling.
> - **Strong Candidate Signals:** Built production-grade SystemC TLM models for 100M+ transaction simulation; Optimized C++ code for 20+ Gbps serial interfaces with <50ns latency; Integrated SystemC models into physical verification flows
> - **Weak / Ambiguous Signals:** Used SystemC for academic projects without production metrics; Mentioned 'strong' without specific performance benchmarks
> - **Screening Question:** How did you optimize C++ code to handle 20+ Gbps serial interfaces with <50ns latency?

### Synopsys Virtualizer / VDK experience.
> **[AI Guidance — Evaluator Aid]**
> - **Concept Summary:** Experience with Synopsys Virtualizer for hardware-software co-simulation and VDK for virtual prototyping.
> - **Strong Candidate Signals:** Deployed Virtualizer for 10M+ transaction simulation in production cycles; Reduced silicon risk by 30% using VDK for early-stage validation; Integrated Virtualizer with physical verification tools
> - **Weak / Ambiguous Signals:** Used Virtualizer for non-production simulations only; Mentioned VDK without quantifiable impact on time-to-market
> - **Screening Question:** How did you reduce silicon risk by 30% using VDK in your last role?

### SoC/system architecture and virtual prototyping.
> **[AI Guidance — Evaluator Aid]**
> - **Concept Summary:** SoC virtual prototyping simulates hardware behavior early in design to catch issues before physical production.
> - **Strong Candidate Signals:** Experience with RTL simulation tools like Synopsys VCS; Proven use of virtual platforms for chip validation in 5nm+ nodes; Quantifiable reduction in hardware defects via prototyping
> - **Weak / Ambiguous Signals:** Mentioned PCIe/CXL without context; Tutorial-level FPGA prototyping projects
> - **Screening Question:** Describe a time you used virtual prototyping to resolve a critical hardware issue before physical silicon.

### PCIe / CXL / UCIe / AMBA.
> **[AI Guidance — Evaluator Aid]**
> - **Concept Summary:** PCIe/CXL/UCIe/AMBA are interconnect protocols enabling high-speed data transfer between chips and systems.
> - **Strong Candidate Signals:** Designed PCIe 5.0/4.0 links in production systems; Implemented CXL 2.0 for memory sharing across GPUs and CPUs; Optimized UCIe for low-latency communication in server clusters
> - **Weak / Ambiguous Signals:** Passive mentions of protocols without implementation details; Academic papers on protocol theory without production deployment
> - **Screening Question:** How did you optimize PCIe/CXL bandwidth in a real system under 100ms latency?

### Strong understanding of AI/HPC infrastructure.
> **[AI Guidance — Evaluator Aid]**
> - **Concept Summary:** AI/HPC infrastructure scales distributed computing for large-scale machine learning workloads.
> - **Strong Candidate Signals:** Deployed 1000+ GPU clusters for training AI models; Managed petabyte-scale data pipelines for real-time inference; Reduced training time by 40% via distributed storage optimization
> - **Weak / Ambiguous Signals:** Generic mentions of 'AI infrastructure'; Small-scale tutorials on cloud ML platforms
> - **Screening Question:** Give an example where you scaled AI infrastructure to handle 1M+ concurrent users.

### Experience working with both RTL and software teams.
> **[AI Guidance — Evaluator Aid]**
> - **Concept Summary:** Collaborating with RTL (hardware) and software teams to integrate chip design and application logic.
> - **Strong Candidate Signals:** Led cross-functional integration of hardware and software in a production system; Documented interface specifications for RTL-to-software handoff
> - **Weak / Ambiguous Signals:** Mentioned 'RTL' without context of team collaboration; Listed as a single task without ownership examples
> - **Screening Question:** Describe a time you resolved a conflict between RTL and software teams during production deployment.

### Chiplet architecture and HBM.
> **[AI Guidance — Evaluator Aid]**
> - **Concept Summary:** Chiplet architecture splits complex SoCs into modular, independent chips for scalability and cost efficiency.
> - **Strong Candidate Signals:** Production chiplet designs with interconnects (e.g., UCIe); HBM memory bandwidth metrics exceeding 500 GB/s; Multi-chip system validation reports
> - **Weak / Ambiguous Signals:** Passive mentions of 'chiplet concepts' without implementation; Tutorial-level HBM simulations without real hardware
> - **Screening Question:** How did you ensure reliable data transfer between chiplets in production?

### AI accelerator/XPU architecture.
> **[AI Guidance — Evaluator Aid]**
> - **Concept Summary:** AI accelerators (XPU) are specialized hardware for high-throughput AI workloads, optimizing inference and training efficiency.
> - **Strong Candidate Signals:** Production AI inference pipelines with 100+ TPUs; Custom XPU firmware for model deployment; Latency metrics below 50us for real-time inference
> - **Weak / Ambiguous Signals:** Passive mentions of 'AI accelerators' without implementation; Tutorial-level model training on generic GPUs
> - **Screening Question:** Give an example where you optimized an XPU pipeline for production latency.

### Emulation platforms such as ZeBu / Palladium / Veloce.
> **[AI Guidance — Evaluator Aid]**
> - **Concept Summary:** Emulation platforms like ZeBu simulate hardware behavior for chip validation without physical devices.
> - **Strong Candidate Signals:** ZeBu or Palladium integration in production test suites; Hardware emulation for real-time chip validation at scale; Production metrics from emulation-driven CI/CD pipelines
> - **Weak / Ambiguous Signals:** Mentioned without context of production use; Tutorial-level emulation projects without metrics
> - **Screening Question:** Have you shipped a production test suite using ZeBu or Palladium for chip validation?

### Python automation.
> **[AI Guidance — Evaluator Aid]**
> - **Concept Summary:** Python automation enables efficient, scalable testing through reusable scripts and frameworks.
> - **Strong Candidate Signals:** Python-based CI/CD pipelines with 90%+ test coverage; Automated regression suites for hardware validation; Metrics showing reduced test cycle time via Python
> - **Weak / Ambiguous Signals:** Passive mentions of 'Python scripting' without context; Tutorial projects without production impact
> - **Screening Question:** Can you share a Python automation that reduced test cycles by 20%+ in production?

### B.E. / B.Tech / M.E. / M.Tech / M.S. in Electronics, Electrical, Computer Engineering, or related discipline.
> **[AI Guidance — Evaluator Aid]**
> - **Concept Summary:** Formal engineering degree in electronics, electrical, or computer engineering disciplines.
> - **Strong Candidate Signals:** Bachelor's/Master's in relevant engineering field from accredited institution; Relevant coursework in digital systems or hardware design
> - **Weak / Ambiguous Signals:** Generic 'engineering background' without degree specifics; Mentioned without context of academic focus
> - **Screening Question:** What specific courses or projects demonstrated your engineering foundation?

### Demonstrated ownership of a virtual platform / VDK architecture used across multiple products or customer configurations.
> **[AI Guidance — Evaluator Aid]**
> - **Concept Summary:** Building and maintaining scalable virtual platforms that support diverse product configurations.
> - **Strong Candidate Signals:** Architected a VDK platform used across 5+ products with 99.5% uptime; Managed configuration pipelines for 10k+ customer instances
> - **Weak / Ambiguous Signals:** Vague references to 'virtual platforms' without metrics; No mention of cross-product ownership
> - **Screening Question:** Walk me through how you scaled your VDK platform during a product launch.

### Experience defining platform architecture spanning compute, connectivity, memory, power, and I/O.
> **[AI Guidance — Evaluator Aid]**
> - **Concept Summary:** Defining hardware-software co-design for end-to-end system performance.
> - **Strong Candidate Signals:** Designed compute/memory hierarchy for AI inference workloads; Optimized I/O pipelines for 10G+ network throughput; Power-aware architecture for edge devices
> - **Weak / Ambiguous Signals:** Mentioned 'system architecture' without specifics; Listed hardware components without integration context
> - **Screening Question:** How did you balance latency and power in your last platform design?

### Strong systems-thinking and architecture leadership across hardware, software, and verification teams.
> **[AI Guidance — Evaluator Aid]**
> - **Concept Summary:** Leading cross-functional teams to align hardware/software goals through technical ownership.
> - **Strong Candidate Signals:** Spearheaded hardware-software co-design for 3+ product launches; Resolved verification bottlenecks across 5+ engineering teams; Defined architecture tradeoffs with quantified impact metrics
> - **Weak / Ambiguous Signals:** Described 'systems thinking' without concrete examples; Referenced team collaboration without ownership metrics
> - **Screening Question:** Give an example where you resolved hardware-software conflicts in production.

### Ability to translate customer XPU requirements into a virtual platform architecture.
> **[AI Guidance — Evaluator Aid]**
> - **Concept Summary:** Mapping customer XPU needs to virtualized platform capabilities.
> - **Strong Candidate Signals:** Virtualized 4+ XPU types for cloud deployments; Translated customer latency requirements into platform specs; Built test frameworks for XPU compatibility
> - **Weak / Ambiguous Signals:** Used 'XPU' without clarifying context; Mentioned virtualization without implementation details
> - **Screening Question:** How did you handle a customer's XPU requirement that conflicted with platform constraints?

### Clear technical communication with RTL, software, and performance teams.
> **[AI Guidance — Evaluator Aid]**
> - **Concept Summary:** Clear technical communication ensures cross-functional alignment on hardware-software interfaces and performance tradeoffs.
> - **Strong Candidate Signals:** Documented interface specifications for RTL-to-software handoffs; Performance metrics from joint debugging sessions; Ownership of latency optimization across teams
> - **Weak / Ambiguous Signals:** Generic mentions of 'cross-team communication'; Tutorial-level collaboration examples without ownership
> - **Screening Question:** Describe a time you resolved a performance bottleneck by aligning RTL, software, and performance teams.

### Prior experience architecting a virtual platform that shipped across more than one customer program.
> **[AI Guidance — Evaluator Aid]**
> - **Concept Summary:** Architecting virtual platforms for multiple customers ensures scalability and reusable validation infrastructure.
> - **Strong Candidate Signals:** Virtual platform shipped to 3+ customer programs with shared components; Cross-customer validation reuse metrics (e.g., 40%+ savings); Production deployment of virtual platforms for chip validation
> - **Weak / Ambiguous Signals:** Single-customer virtual platforms without scalability; Conceptual designs without production shipping
> - **Screening Question:** Describe a virtual platform you shipped to multiple customers with shared validation components.

### Direct exposure to correlating TLM models against RTL/emulation results.
> **[AI Guidance — Evaluator Aid]**
> - **Concept Summary:** Correlating TLM (Transaction-Level Modeling) models with RTL/emulation results identifies discrepancies in hardware design before silicon release, ensuring accurate simulation of complex SoC behavior.
> - **Strong Candidate Signals:** Quantitative discrepancy reports from UVM-based verification platforms; Production-ready TLM-to-RTL correlation scripts for 100M+ transaction throughput; Emulation environment integration with Synopsys VCS or Cadence Incisive
> - **Weak / Ambiguous Signals:** Mention of TLM without specific correlation metrics; Tutorial-level RTL verification projects without production deployment
> - **Screening Question:** Describe a production system where you reduced RTL-emulation discrepancies by 50%+ using TLM correlation.

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

