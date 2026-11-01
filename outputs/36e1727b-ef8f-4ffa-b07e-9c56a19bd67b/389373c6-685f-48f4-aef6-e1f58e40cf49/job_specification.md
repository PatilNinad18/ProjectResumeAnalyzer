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
> - **Concept Summary:** 10-15+ years in semiconductor/system engineering for complex hardware design and production.
> - **Strong Candidate Signals:** Designed silicon IP for 7nm+ nodes; Led teams through 3+ major product launches; Published patents in semiconductor manufacturing
> - **Weak / Ambiguous Signals:** Worked on academic projects without production deployment; Mentioned 'semiconductor experience' without specific hardware focus
> - **Screening Question:** Can you describe a silicon IP design you led from 7nm to production?

### Strong C++ and SystemC/TLM.
> **[AI Guidance — Evaluator Aid]**
> - **Concept Summary:** C++ for high-performance systems and SystemC/TLM for hardware modeling and simulation.
> - **Strong Candidate Signals:** Built real-time simulation models using SystemC TLM; Optimized C++ code for 100+ Gbps data paths; Integrated SystemC with physical design tools
> - **Weak / Ambiguous Signals:** Used C++ in academic projects without performance metrics; Mentioned SystemC but not in production environments
> - **Screening Question:** How did you optimize C++ for high-speed data paths in your last role?

### Synopsys Virtualizer / VDK experience.
> **[AI Guidance — Evaluator Aid]**
> - **Concept Summary:** Synopsys Virtualizer for hardware-software co-simulation and virtual prototyping.
> - **Strong Candidate Signals:** Deployed Synopsys Virtualizer for 100M+ device simulations; Reduced silicon risk by 30% using Virtualizer; Integrated Virtualizer with physical design flows
> - **Weak / Ambiguous Signals:** Used Virtualizer in lab environments without production impact; Mentioned Virtualizer but not tied to hardware validation
> - **Screening Question:** How did you measure Virtualizer's impact on silicon risk reduction?

### SoC/system architecture and virtual prototyping.
> **[AI Guidance — Evaluator Aid]**
> - **Concept Summary:** SoC/system architecture defines hardware layers for integrated computing; virtual prototyping tests designs before physical production to reduce costs and risks.
> - **Strong Candidate Signals:** Experience with FPGA-based system simulation tools like Vitis; Proven track record of reducing hardware iteration cycles by 30%+ through virtual prototyping
> - **Weak / Ambiguous Signals:** Mentioned 'virtual prototyping' without specific tools or metrics; Projects using only simulation without hardware validation
> - **Screening Question:** How have you reduced hardware development costs using virtual prototyping in a production system?

### PCIe / CXL / UCIe / AMBA.
> **[AI Guidance — Evaluator Aid]**
> - **Concept Summary:** PCIe/CXL/UCIe/AMBA are high-speed interconnect standards enabling efficient data transfer between CPUs, memory, and accelerators in modern hardware systems.
> - **Strong Candidate Signals:** Deployed PCIe 4.0+ or CXL 1.0+ in production systems; Experience with AMBA4 for SoC interconnect design
> - **Weak / Ambiguous Signals:** Listed standards without implementation context; Projects using only PCIe without performance metrics
> - **Screening Question:** Describe a production system where you optimized data transfer using PCIe/CXL/UCIe.

### Strong understanding of AI/HPC infrastructure.
> **[AI Guidance — Evaluator Aid]**
> - **Concept Summary:** AI/HPC infrastructure involves scalable computing resources for large-scale AI training and inference workloads, critical for handling massive datasets and complex models.
> - **Strong Candidate Signals:** Managed 100+ GPU clusters for AI training pipelines; Deployed MLOps systems with 95%+ model accuracy retention
> - **Weak / Ambiguous Signals:** Mentioned 'AI/HPC' without specific infrastructure scale; Projects using cloud-based AI without cluster management ownership
> - **Screening Question:** How have you scaled AI training infrastructure to handle 10x workload increases?

### Experience working with both RTL and software teams.
> **[AI Guidance — Evaluator Aid]**
> - **Concept Summary:** Collaborating with hardware teams to design and validate silicon-level circuits while coordinating software development for system integration.
> - **Strong Candidate Signals:** Led RTL-to-software handoff for production IoT devices; Coordinated cross-functional teams on 5+ product launches with silicon validation
> - **Weak / Ambiguous Signals:** Mentioned 'RTL and software collaboration' without specifics; Participated in meetings but no ownership of integration
> - **Screening Question:** Describe a time you resolved a silicon validation conflict between hardware and software teams during production.

### Chiplet architecture and HBM.
> **[AI Guidance — Evaluator Aid]**
> - **Concept Summary:** Chiplet architecture splits complex chips into smaller, independent modules for scalability and cost efficiency in high-performance computing.
> - **Strong Candidate Signals:** Production chiplets with HBM2E memory interfaces; Custom interconnects for chiplet communication in 5nm+ processes; Performance benchmarks showing <10ns latency between chiplets
> - **Weak / Ambiguous Signals:** Generic 'exposure to chiplet' without implementation details; Mentions of chiplets without HBM or specific process nodes
> - **Screening Question:** How did you optimize memory bandwidth in a chiplet system with HBM?

### AI accelerator/XPU architecture.
> **[AI Guidance — Evaluator Aid]**
> - **Concept Summary:** AI accelerators (XPU) are specialized hardware units for high-throughput AI workloads, reducing latency and power consumption versus general-purpose CPUs.
> - **Strong Candidate Signals:** Deployment of 10+ TFLOPS AI accelerators in production inference systems; Customized XPU kernels for specific AI models with <50ms latency; Power efficiency metrics (e.g., 3x lower than CPU for same workload)
> - **Weak / Ambiguous Signals:** Passive mentions of 'AI accelerators' without metrics or ownership; Tutorial-level projects using pre-built XPU frameworks
> - **Screening Question:** Share a production example where you improved inference latency using an XPU.

### Emulation platforms such as ZeBu / Palladium / Veloce.
> **[AI Guidance — Evaluator Aid]**
> - **Concept Summary:** Emulation platforms like ZeBu provide hardware-level simulation for chip verification, enabling faster silicon validation without physical hardware.
> - **Strong Candidate Signals:** Built production-grade emulation flows using ZeBu for ASIC validation; Reduced silicon tapeout time by 30%+ via emulation; Integrated emulation with CI/CD pipelines for automated regression testing
> - **Weak / Ambiguous Signals:** Mentioned ZeBu in a tutorial without implementation details; Used emulation for non-production testing only
> - **Screening Question:** How did you quantify the impact of your emulation platform on silicon tapeout time?

### Python automation.
> **[AI Guidance — Evaluator Aid]**
> - **Concept Summary:** Python automation streamlines complex verification workflows through reusable scripts and integrated toolchains.
> - **Strong Candidate Signals:** Automated 100+ test cases with Python in CI/CD pipelines; Reduced manual test setup time by 50% using Python scripts; Integrated Python with VCS for automated regression testing
> - **Weak / Ambiguous Signals:** Used Python for simple script tasks without automation impact; Mentioned Python in a project without measurable outcomes
> - **Screening Question:** Can you share a specific example where Python automation improved your verification throughput?

### B.E. / B.Tech / M.E. / M.Tech / M.S. in Electronics, Electrical, Computer Engineering, or related discipline.
> **[AI Guidance — Evaluator Aid]**
> - **Concept Summary:** Formal engineering degree in electronics, electrical, or computer engineering disciplines for foundational technical rigor.
> - **Strong Candidate Signals:** Bachelor's/Master's in Electrical Engineering with relevant coursework; Academic projects involving hardware design or embedded systems
> - **Weak / Ambiguous Signals:** Generic 'computer science' degree without hardware focus; Mentioned engineering but no specific discipline or coursework
> - **Screening Question:** What engineering courses or projects demonstrate your hardware-focused background?

### Demonstrated ownership of a virtual platform / VDK architecture used across multiple products or customer configurations.
> **[AI Guidance — Evaluator Aid]**
> - **Concept Summary:** Building reusable virtual platform infrastructure that supports multiple product variants through configuration-driven approaches.
> - **Strong Candidate Signals:** Deployed VDK for 100k+ user products with <2% config drift; Reduced integration time by 40% via modular VDK components
> - **Weak / Ambiguous Signals:** Virtual platform as a buzzword without metrics; Mentioned 'multiple products' without ownership or scale
> - **Screening Question:** Walk me through how you scaled a virtual platform to support 5+ product variants.

### Experience defining platform architecture spanning compute, connectivity, memory, power, and I/O.
> **[AI Guidance — Evaluator Aid]**
> - **Concept Summary:** Designing hardware-software co-optimized systems for real-world performance constraints.
> - **Strong Candidate Signals:** Defined compute/memory hierarchy in production IoT platforms; Optimized I/O latency for 10k+ concurrent devices; Power-aware architecture for edge deployments
> - **Weak / Ambiguous Signals:** Mentioned 'system architecture' without hardware specifics; Basic cloud infrastructure setup without optimization goals
> - **Screening Question:** Describe a time you reduced latency by 30%+ in a real production system with hardware constraints.

### Strong systems-thinking and architecture leadership across hardware, software, and verification teams.
> **[AI Guidance — Evaluator Aid]**
> - **Concept Summary:** Leading cross-functional hardware/software teams to align on scalable, reliable system designs.
> - **Strong Candidate Signals:** Led 5+ team integrations for hardware-software co-design cycles; Reduced verification cycle time by 40% through architecture decisions; Defined SLAs for hardware reliability across distributed teams
> - **Weak / Ambiguous Signals:** Said 'good systems thinking' without concrete examples; Only mentioned software architecture without hardware context
> - **Screening Question:** How did you resolve a conflict between hardware and software teams during a critical deadline?

### Ability to translate customer XPU requirements into a virtual platform architecture.
> **[AI Guidance — Evaluator Aid]**
> - **Concept Summary:** Mapping customer-specific hardware capabilities to virtualized platform solutions.
> - **Strong Candidate Signals:** Virtualized XPU architectures for 5+ customer workloads; Customized memory allocation strategies for specific XPU types; Quantified performance gains from XPU-to-virtual mapping
> - **Weak / Ambiguous Signals:** Generic 'XPU compatibility' statements without implementation; Tutorial-level virtualization projects without production metrics
> - **Screening Question:** Give an example where you adapted a virtual platform to meet a customer's unique XPU constraints.

### Clear technical communication with RTL, software, and performance teams.
> **[AI Guidance — Evaluator Aid]**
> - **Concept Summary:** Clear communication bridges RTL (hardware design), software teams, and performance metrics to ensure hardware-software co-design.
> - **Strong Candidate Signals:** Documented cross-functional specs with RTL, software, and perf teams; Production system debugging logs showing joint root cause analysis; Ownership of hardware-software handoff in live deployments
> - **Weak / Ambiguous Signals:** Mention of 'communication' without specific teams or metrics; Passive phrases like 'works well with' without ownership examples
> - **Screening Question:** Describe a time you resolved a critical hardware-software conflict during production deployment.

### Prior experience architecting a virtual platform that shipped across more than one customer program.
> **[AI Guidance — Evaluator Aid]**
> - **Concept Summary:** Architecting virtual platforms that ship across multiple customer programs ensures scalable, reusable verification infrastructure.
> - **Strong Candidate Signals:** Designed virtual platform used in 3+ customer programs with shared codebase; Maintained platform across 2+ major product lines with minimal rework; Delivered virtual platform for production use with 95%+ test coverage
> - **Weak / Ambiguous Signals:** Virtual platform for single project without cross-program usage; Platform that required significant rework per customer program
> - **Screening Question:** What was the scale of your virtual platform's adoption across customer programs?

### Direct exposure to correlating TLM models against RTL/emulation results.
> **[AI Guidance — Evaluator Aid]**
> - **Concept Summary:** Correlating TLM (Transaction Level Modeling) simulations with RTL (Register-Transfer Level) code ensures accurate hardware behavior prediction before physical implementation.
> - **Strong Candidate Signals:** Published TLM-to-RTL correlation reports in production silicon validation; RTL verification coverage metrics exceeding 95% with TLM models; Emulation results from Synopsys VCS or Cadence Incisive
> - **Weak / Ambiguous Signals:** Mentioned TLM in design docs without implementation details; Tutorial-level TLM simulations without production integration
> - **Screening Question:** Have you led a production TLM-RTL correlation effort that reduced silicon bugs by 20%+?

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

