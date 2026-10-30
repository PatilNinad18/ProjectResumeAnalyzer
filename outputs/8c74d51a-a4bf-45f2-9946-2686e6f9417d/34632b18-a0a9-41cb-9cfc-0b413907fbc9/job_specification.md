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
> - **Concept Summary:** 10-15+ years building semiconductor systems from silicon to production.
> - **Strong Candidate Signals:** Experience with full chip signoff in 7nm+ processes; Ownership of complex SoC architectures across multiple product cycles; Published papers or patents in semiconductor design
> - **Weak / Ambiguous Signals:** Mentioned 'semiconductor experience' without process node specifics; Projects limited to academic simulations without real-world deployment
> - **Screening Question:** Can you describe a recent SoC design cycle you led from silicon to production?

### Strong C++ and SystemC/TLM.
> **[AI Guidance — Evaluator Aid]**
> - **Concept Summary:** C++ for high-performance systems and SystemC/TLM for hardware modeling.
> - **Strong Candidate Signals:** Production C++ codebases handling >1M I/O operations/sec; SystemC TLM models used in physical verification flows; Optimized C++ kernels for FPGA deployment
> - **Weak / Ambiguous Signals:** Tutorial-level SystemC projects without performance metrics; C++ experience limited to academic exercises
> - **Screening Question:** How have you optimized C++ code for hardware acceleration in production systems?

### Synopsys Virtualizer / VDK experience.
> **[AI Guidance — Evaluator Aid]**
> - **Concept Summary:** Synopsys Virtualizer enables hardware-software co-simulation for early validation.
> - **Strong Candidate Signals:** Virtualizer usage in 100+ node co-simulation environments; Production-ready VDK models for complex SoC validation; Integration with physical design tools like VCS
> - **Weak / Ambiguous Signals:** Mentioned Virtualizer without specific use cases or metrics; Virtualizer projects limited to small-scale simulations
> - **Screening Question:** Can you share a production example where Virtualizer reduced validation time?

### SoC/system architecture and virtual prototyping.
> **[AI Guidance — Evaluator Aid]**
> - **Concept Summary:** SoC architecture defines integrated hardware for processing, memory, and I/O, prototyped in simulation before physical deployment to reduce risks.
> - **Strong Candidate Signals:** Experience with SystemVerilog or UVM for SoC simulation; Production-ready virtual prototypes for hardware validation
> - **Weak / Ambiguous Signals:** Mention of 'SoC' without specific prototyping tools; Tutorial-level FPGA projects without real-world integration
> - **Screening Question:** Have you built a virtual prototype that accelerated hardware validation by 30%+ in production?

### PCIe / CXL / UCIe / AMBA.
> **[AI Guidance — Evaluator Aid]**
> - **Concept Summary:** PCIe/CXL/UCIe/AMBA are interconnect standards enabling high-speed, low-latency communication between chips and systems.
> - **Strong Candidate Signals:** Implementation of CXL 3.0 for memory sharing in AI clusters; PCIe 5.0 or higher in production infrastructure
> - **Weak / Ambiguous Signals:** Passive mentions of 'PCIe' without specific versions; UCIe implementations limited to lab environments
> - **Screening Question:** Which interconnect standard have you used for cross-chip memory sharing in production?

### Strong understanding of AI/HPC infrastructure.
> **[AI Guidance — Evaluator Aid]**
> - **Concept Summary:** AI/HPC infrastructure involves scalable compute, storage, and networking optimized for large-scale AI training and high-performance workloads.
> - **Strong Candidate Signals:** Deployed 100+ GPU nodes for AI training clusters; Customized storage solutions for petabyte-scale AI datasets
> - **Weak / Ambiguous Signals:** Generic references to 'AI infrastructure' without metrics; Academic projects with no production deployment
> - **Screening Question:** How many production AI training nodes have you managed?

### Experience working with both RTL and software teams.
> **[AI Guidance — Evaluator Aid]**
> - **Concept Summary:** Collaborating with hardware teams to translate circuit designs into software interfaces for seamless integration.
> - **Strong Candidate Signals:** Led RTL-to-software handoff in 2+ product launches; Coordinated cross-functional sprints with hardware teams; Documented interface specs for 100k+ device integrations
> - **Weak / Ambiguous Signals:** Mentioned 'RTL collaboration' without specifics; Listed team names but no ownership metrics
> - **Screening Question:** Describe a time you resolved a conflict between RTL and software teams during a product launch.

### Chiplet architecture and HBM.
> **[AI Guidance — Evaluator Aid]**
> - **Concept Summary:** Chiplet architecture uses multiple smaller, specialized chips (chiplets) connected via high-speed interconnects for complex SoCs.
> - **Strong Candidate Signals:** Experience with Intel's 3D chiplet tech or AMD's Infinity Cache; Production of chiplets with HBM memory interfaces
> - **Weak / Ambiguous Signals:** Mention of 'chiplet' without specific interconnect protocols or memory types
> - **Screening Question:** How have you implemented chiplet communication in a production system with HBM?

### AI accelerator/XPU architecture.
> **[AI Guidance — Evaluator Aid]**
> - **Concept Summary:** AI accelerators (XPU) are specialized hardware units optimized for machine learning workloads, like Tensor Cores in NVIDIA GPUs.
> - **Strong Candidate Signals:** Deployment of custom AI accelerators with 100+ TFLOPS performance; Integration of XPU with framework-specific APIs (e.g., TensorFlow Lite)
> - **Weak / Ambiguous Signals:** Passive mentions of 'AI accelerators' without production metrics
> - **Screening Question:** Show me a production metric where your XPU improved inference latency.

### Emulation platforms such as ZeBu / Palladium / Veloce.
> **[AI Guidance — Evaluator Aid]**
> - **Concept Summary:** Emulation platforms like ZeBu simulate hardware for chip validation without physical devices.
> - **Strong Candidate Signals:** Built production-grade emulation test suites using ZeBu; Reduced hardware costs by 40% through emulation in customer deployments
> - **Weak / Ambiguous Signals:** Mentioned ZeBu in a tutorial project without integration; Used emulation for simulation only, not production validation
> - **Screening Question:** Have you shipped an emulation platform that handled >10k test cases per day?

### Python automation.
> **[AI Guidance — Evaluator Aid]**
> - **Concept Summary:** Python automation streamlines repetitive tasks and integrates with CI/CD pipelines for faster releases.
> - **Strong Candidate Signals:** Automated 50+ test cases per hour using Python in CI/CD; Reduced release cycles from weeks to days via Python scripts
> - **Weak / Ambiguous Signals:** Wrote Python scripts for simple task automation without metrics; Used Python for personal projects, not production systems
> - **Screening Question:** Can you share a Python automation that reduced deployment time by 50%?

### B.E. / B.Tech / M.E. / M.Tech / M.S. in Electronics, Electrical, Computer Engineering, or related discipline.
> **[AI Guidance — Evaluator Aid]**
> - **Concept Summary:** Formal engineering degree in electronics, electrical, or computer engineering disciplines.
> - **Strong Candidate Signals:** B.E. in Electronics with 4+ years of semiconductor design experience; M.Tech in Computer Engineering with thesis on embedded systems; Relevant coursework: VLSI, digital logic design, microcontrollers
> - **Weak / Ambiguous Signals:** Generic 'computer engineering' degree without specialization; No mention of relevant coursework or projects
> - **Screening Question:** What specific electronics courses did you take that relate to your current role?

### Demonstrated ownership of a virtual platform / VDK architecture used across multiple products or customer configurations.
> **[AI Guidance — Evaluator Aid]**
> - **Concept Summary:** Building scalable virtual platforms that support diverse product configurations through shared architecture.
> - **Strong Candidate Signals:** Built VDK for 5+ products with 90% reuse rate; Reduced config time from weeks to hours via template automation; Managed 10k+ customer-specific configurations
> - **Weak / Ambiguous Signals:** Mentioned 'virtual platform' without technical scope; No metrics on scalability or customer impact
> - **Screening Question:** How did you measure the impact of your VDK architecture on product delivery?

### Experience defining platform architecture spanning compute, connectivity, memory, power, and I/O.
> **[AI Guidance — Evaluator Aid]**
> - **Concept Summary:** Defining platform architecture that integrates hardware compute, network, memory, power, and I/O subsystems for scalable production systems.
> - **Strong Candidate Signals:** Designed heterogeneous compute platforms with NVIDIA GPUs and AMD EPYC CPUs; Optimized memory bandwidth via PCIe 5.0 interconnects in production clusters; Reduced power consumption by 22% through custom power management in high-throughput systems
> - **Weak / Ambiguous Signals:** Mentioned 'platform architecture' without specific hardware components; Referenced generic 'scalable systems' without metrics or ownership
> - **Screening Question:** Describe a time you designed a platform where you quantified power savings from hardware optimization.

### Strong systems-thinking and architecture leadership across hardware, software, and verification teams.
> **[AI Guidance — Evaluator Aid]**
> - **Concept Summary:** Leading cross-functional architecture decisions that align hardware, software, and verification teams toward production-ready solutions.
> - **Strong Candidate Signals:** Led hardware/software co-design for a 10k+ node cluster with zero downtime migration; Orchestrated verification team to validate architecture changes before production deployment; Reduced cross-team handoff time by 40% through shared architecture documentation
> - **Weak / Ambiguous Signals:** Claimed 'systems thinking' without specific team coordination examples; Referenced 'architecture leadership' without ownership of production outcomes
> - **Screening Question:** Give an example where you resolved a conflict between hardware and software teams over architecture decisions.

### Ability to translate customer XPU requirements into a virtual platform architecture.
> **[AI Guidance — Evaluator Aid]**
> - **Concept Summary:** Translating customer-specific accelerator requirements into virtualized platform architectures that meet performance and compliance needs.
> - **Strong Candidate Signals:** Virtualized XPU workloads using Kubernetes with custom drivers for NVIDIA A100s; Achieved 95% latency compliance for customer XPU requirements in production environments; Integrated security policies for XPU data without performance degradation
> - **Weak / Ambiguous Signals:** Mentioned 'XPU requirements' without specifying customer or technical constraints; Referenced 'virtual platform' without metrics on performance or compliance
> - **Screening Question:** Walk me through how you mapped a customer's XPU requirement to your virtual platform architecture.

### Clear technical communication with RTL, software, and performance teams.
> **[AI Guidance — Evaluator Aid]**
> - **Concept Summary:** Clear technical communication ensures cross-functional alignment on hardware-software interfaces and performance bottlenecks in chip design.
> - **Strong Candidate Signals:** Documented interface specifications for RTL-to-software handoffs; Performance metrics tied to specific hardware-software interactions
> - **Weak / Ambiguous Signals:** Vague statements about 'good communication' without concrete examples
> - **Screening Question:** Describe a time you resolved a performance bottleneck between RTL and software teams during chip development.

### Prior experience architecting a virtual platform that shipped across more than one customer program.
> **[AI Guidance — Evaluator Aid]**
> - **Concept Summary:** Architecting virtual platforms that ship across multiple customer programs ensures scalability and reuse of validation assets.
> - **Strong Candidate Signals:** Led virtual platform for 3+ customer programs with shared test infrastructure; Reduced validation time by 30% through reusable components
> - **Weak / Ambiguous Signals:** Designed virtual platforms for single projects without cross-program reuse; Virtual platforms only used in development, not production
> - **Screening Question:** Describe a virtual platform you shipped that served multiple customers.

### Direct exposure to correlating TLM models against RTL/emulation results.
> **[AI Guidance — Evaluator Aid]**
> - **Concept Summary:** Correlating TLM (Transaction Level Modeling) simulations with RTL (Register Transfer Level) code ensures accurate hardware behavior validation before silicon release.
> - **Strong Candidate Signals:** Built TLM models in SystemVerilog for chip-level simulation; Produced correlation reports showing <0.1% discrepancy between TLM and RTL results; Used commercial emulation tools like Synopsys VCS for production validation
> - **Weak / Ambiguous Signals:** Mentioned TLM without specific frameworks; Listed TLM as a learning topic without implementation
> - **Screening Question:** Have you built TLM models that directly correlated with RTL results in production silicon validation?

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

