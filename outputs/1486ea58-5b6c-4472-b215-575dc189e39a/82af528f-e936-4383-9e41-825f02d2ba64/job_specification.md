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
> - **Strong Candidate Signals:** Published semiconductor design documentation for 10+ years; Ownership of production-grade ASIC/SoC projects with 100M+ transistors; Direct involvement in silicon sign-off for 3+ product cycles
> - **Weak / Ambiguous Signals:** Academic semiconductor coursework without industry implementation; Passive mentions of 'semiconductor experience' without specific projects
> - **Screening Question:** Describe a production silicon sign-off you led for an ASIC with >100M transistors.

### Strong C++ and SystemC/TLM.
> **[AI Guidance — Evaluator Aid]**
> - **Concept Summary:** C++ enables high-performance system programming, while SystemC/TLM provides hardware modeling for complex system verification.
> - **Strong Candidate Signals:** Production C++ codebase with 1M+ lines of verified functionality; SystemC TLM models used in formal verification for 500K+ transaction paths; Experience with C++/SystemC co-simulation for hardware-software interfaces
> - **Weak / Ambiguous Signals:** Tutorial-level SystemC projects without production integration; C++ experience limited to academic exercises or non-production tools
> - **Screening Question:** Show an example of C++ code that directly interfaces with a SystemC TLM model in production.

### Synopsys Virtualizer / VDK experience.
> **[AI Guidance — Evaluator Aid]**
> - **Concept Summary:** Synopsys Virtualizer enables hardware-software co-simulation using virtualized silicon models for faster verification cycles.
> - **Strong Candidate Signals:** Production deployment of Virtualizer for 100M+ transistor designs; Experience with VDK for hardware-software co-simulation in 3+ product cycles; Reduced verification time by >50% using Virtualizer in production systems
> - **Weak / Ambiguous Signals:** Virtualizer/VDK mentioned in job descriptions without implementation; Non-production use of Virtualizer for academic simulations only
> - **Screening Question:** How did you measure the impact of Virtualizer on your verification cycle time?

### SoC/system architecture and virtual prototyping.
> **[AI Guidance — Evaluator Aid]**
> - **Concept Summary:** SoC design integrates hardware and software for efficient prototyping before full system deployment.
> - **Strong Candidate Signals:** Built custom SoC prototypes using RTL simulation tools like Vivado; Reduced hardware validation time by 30% through virtual prototyping
> - **Weak / Ambiguous Signals:** Mentioned SoC in academic projects without implementation; Used generic terms like 'virtual prototyping' without metrics
> - **Screening Question:** How did you reduce hardware validation cycles using virtual prototyping?

### PCIe / CXL / UCIe / AMBA.
> **[AI Guidance — Evaluator Aid]**
> - **Concept Summary:** PCIe, CXL, UCIe, and AMBA are hardware interconnect protocols for high-speed data transfer between chips.
> - **Strong Candidate Signals:** Implemented PCIe 5.0 switches in production systems; Optimized CXL traffic with UCIe for low-latency memory access
> - **Weak / Ambiguous Signals:** Listed protocols without implementation context; Used protocol names without specifying hardware targets
> - **Screening Question:** What specific hardware metrics did you improve using PCIe/CXL?

### Strong understanding of AI/HPC infrastructure.
> **[AI Guidance — Evaluator Aid]**
> - **Concept Summary:** AI/HPC infrastructure supports large-scale machine learning workloads with scalable compute and storage.
> - **Strong Candidate Signals:** Deployed 100+ GPU nodes for distributed training pipelines; Reduced inference latency by 40% using optimized storage tiers
> - **Weak / Ambiguous Signals:** Mentioned AI infrastructure without quantifiable results; Referenced cloud services without on-prem deployment experience
> - **Screening Question:** How did you scale AI training while maintaining low latency?

### Experience working with both RTL and software teams.
> **[AI Guidance — Evaluator Aid]**
> - **Concept Summary:** Collaborating with hardware teams to translate circuit designs into software interfaces.
> - **Strong Candidate Signals:** RTL simulation results integrated into CI/CD pipelines; Joint architecture reviews with hardware engineers; Cross-team feature delivery timelines
> - **Weak / Ambiguous Signals:** Mentioned but no concrete examples; Generic 'collaboration' without metrics
> - **Screening Question:** Describe a specific project where you bridged RTL and software teams to meet a deadline.

### Chiplet architecture and HBM.
> **[AI Guidance — Evaluator Aid]**
> - **Concept Summary:** Chiplet architecture combines multiple smaller chips into a single system using high-bandwidth interconnects for scalability.
> - **Strong Candidate Signals:** Experience with 3D chip stacking or silicon interconnects in production systems; Design of chiplet-based AI accelerators with HBM memory interfaces; Quantifiable performance gains from chiplet integration
> - **Weak / Ambiguous Signals:** Tutorial-level chiplet diagrams without implementation details; Mentions of 'chiplet' without hardware ownership
> - **Screening Question:** How did you optimize memory bandwidth in a chiplet design with HBM?

### AI accelerator/XPU architecture.
> **[AI Guidance — Evaluator Aid]**
> - **Concept Summary:** AI accelerators (XPU) are specialized hardware units for high-performance AI workloads, reducing software overhead.
> - **Strong Candidate Signals:** Deployment of custom AI accelerators with quantized models; End-to-end inference latency metrics for production AI systems; Hardware-software co-design for model deployment
> - **Weak / Ambiguous Signals:** Generic mentions of 'AI accelerators' without specific use cases; Academic projects with no production metrics
> - **Screening Question:** What was your most impactful optimization in an AI accelerator's inference pipeline?

### Emulation platforms such as ZeBu / Palladium / Veloce.
> **[AI Guidance — Evaluator Aid]**
> - **Concept Summary:** Emulation platforms like ZeBu simulate hardware behavior for chip validation without physical devices.
> - **Strong Candidate Signals:** ZeBu or Palladium in production chip validation flow; Hardware debug sessions with customer-specific test cases; Production metrics: 95%+ pass rate on critical paths
> - **Weak / Ambiguous Signals:** Mentioned in tutorials without implementation details; Limited to simulation without hardware integration
> - **Screening Question:** Have you shipped a production chip validation flow using ZeBu/Palladium with customer-specific test cases?

### Python automation.
> **[AI Guidance — Evaluator Aid]**
> - **Concept Summary:** Python automation streamlines repetitive tasks in CI/CD pipelines and hardware testing workflows.
> - **Strong Candidate Signals:** Python scripts reducing test setup time by 50%+ in production; Integration with JUnit or pytest for hardware test automation; Production metrics: 99.9% test pass rate via Python
> - **Weak / Ambiguous Signals:** Basic Python tutorials without real-world testing integration; Manual test execution without automation metrics
> - **Screening Question:** Can you share a Python automation that reduced test setup time by 50%+ in production?

### B.E. / B.Tech / M.E. / M.Tech / M.S. in Electronics, Electrical, Computer Engineering, or related discipline.
> **[AI Guidance — Evaluator Aid]**
> - **Concept Summary:** Formal engineering degree in electronics, electrical, or computer engineering disciplines.
> - **Strong Candidate Signals:** Degree from accredited engineering program; Relevant coursework in digital systems or VLSI design; Academic projects with hardware/software integration
> - **Weak / Ambiguous Signals:** Generic 'computer science' degrees without hardware focus; Self-study certifications without formal degrees
> - **Screening Question:** What engineering coursework or projects involved hardware-software interfaces?

### Demonstrated ownership of a virtual platform / VDK architecture used across multiple products or customer configurations.
> **[AI Guidance — Evaluator Aid]**
> - **Concept Summary:** Designing and maintaining a virtual platform that scales across products and customer configurations.
> - **Strong Candidate Signals:** Production VDK architecture with 10k+ active configurations; Cross-product feature rollouts via the platform; Metrics tracking platform adoption per product line
> - **Weak / Ambiguous Signals:** Prototype-level virtual platforms; Single-product implementations without scalability
> - **Screening Question:** Walk me through a VDK architecture you owned that handled multiple product configurations.

### Experience defining platform architecture spanning compute, connectivity, memory, power, and I/O.
> **[AI Guidance — Evaluator Aid]**
> - **Concept Summary:** Defining hardware-software integration for scalable compute workloads across physical and virtual environments.
> - **Strong Candidate Signals:** Designed compute clusters with 10k+ nodes using Kubernetes; Optimized memory bandwidth via NVMe SSDs in production systems; Reduced power consumption by 25% through I/O virtualization
> - **Weak / Ambiguous Signals:** Mentioned 'hardware-software integration' without specifics; Listed protocols without implementation context
> - **Screening Question:** Describe a time you reduced latency in a distributed system by optimizing I/O paths.

### Strong systems-thinking and architecture leadership across hardware, software, and verification teams.
> **[AI Guidance — Evaluator Aid]**
> - **Concept Summary:** Leading cross-functional architecture decisions that align hardware capabilities with software requirements.
> - **Strong Candidate Signals:** Led hardware-software tradeoffs for 5+ teams in a production system; Defined verification protocols for 100k+ components across teams; Reduced integration delays by 40% through architecture ownership
> - **Weak / Ambiguous Signals:** Vague statements about 'alignment' without metrics; Passive mentions of team coordination without ownership
> - **Screening Question:** How did you resolve a conflict between hardware and software teams over architecture decisions?

### Ability to translate customer XPU requirements into a virtual platform architecture.
> **[AI Guidance — Evaluator Aid]**
> - **Concept Summary:** Mapping customer XPU specifications to virtualized platform capabilities for real-world deployment.
> - **Strong Candidate Signals:** Translated XPU specs into virtual platforms with 95%+ utilization; Built test environments matching customer hardware constraints; Achieved 10x faster validation cycles through abstraction layers
> - **Weak / Ambiguous Signals:** Generic references to 'translating requirements'; No mention of production deployment metrics
> - **Screening Question:** Give an example where you adapted a virtual platform for customer XPU constraints.

### Clear technical communication with RTL, software, and performance teams.
> **[AI Guidance — Evaluator Aid]**
> - **Concept Summary:** Clear technical communication across RTL, software, and performance teams ensures alignment on hardware-software interfaces and timing constraints.
> - **Strong Candidate Signals:** Documented cross-team meeting minutes with specific RTL/software/performance decisions; Ownership of production silicon validation timelines; Real-time debug coordination during chip bring-up
> - **Weak / Ambiguous Signals:** Mention of 'good communication' without concrete examples; Passive participation in meetings without ownership
> - **Screening Question:** Describe a time you resolved a critical timing conflict between RTL and software teams during chip validation.

### Prior experience architecting a virtual platform that shipped across more than one customer program.
> **[AI Guidance — Evaluator Aid]**
> - **Concept Summary:** Architecting virtual platforms for multiple customers requires scalable, reusable infrastructure across programs.
> - **Strong Candidate Signals:** Virtual platform shipped to 3+ customers with unique test cases; Shared infrastructure reduced development time by 40%+; Production metrics: 98%+ platform stability across customer environments
> - **Weak / Ambiguous Signals:** Single-customer virtual platforms without scalability; Theoretical designs without production shipping
> - **Screening Question:** Describe a virtual platform you shipped to 3+ customers with unique test cases.

### Direct exposure to correlating TLM models against RTL/emulation results.
> **[AI Guidance — Evaluator Aid]**
> - **Concept Summary:** Correlating TLM models with RTL/emulation results ensures simulation accuracy by matching behavioral models against actual hardware execution.
> - **Strong Candidate Signals:** Built TLM models that reduced debug cycles by 30% in production silicon; Integrated TLM with emulation platforms like EDA tools for real-time validation; Published correlation metrics tracking model vs. RTL divergence
> - **Weak / Ambiguous Signals:** Mentioned TLM without specific validation metrics; Used TLM in academic projects without production deployment
> - **Screening Question:** Have you quantified TLM model accuracy against RTL in a real production system?

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

