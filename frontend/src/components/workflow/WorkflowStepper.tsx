import type { WorkflowPageProps } from "./WorkflowPage";
import styles from "./WorkflowStepper.module.css";

type WorkflowStepperProps = Pick<WorkflowPageProps, "isStep1Done" | "isStep2Done" | "currentStep" | "isStep3Done" | "isStep4Done" | "isStep5Done">;

export default function WorkflowStepper({
    isStep1Done,
    isStep2Done,
    currentStep,
    isStep3Done,
    isStep4Done,
    isStep5Done,
}: WorkflowStepperProps) {
  return (
    <>
      <div className={`${styles.workflowStepper} stepper`}>
        <div className={`step-item ${isStep1Done ? "completed" : "active"}`}>
          <div className="step-circle">{isStep1Done ? "✓" : "1"}</div>
          <span className="step-label">Company Details</span>
        </div>
        <div className={`step-item ${isStep2Done ? "completed" : currentStep === 2 ? "active" : ""}`}>
          <div className="step-circle">{isStep2Done ? "✓" : "2"}</div>
          <span className="step-label">Enter / Upload JD</span>
        </div>
        <div className={`step-item ${isStep3Done ? "completed" : currentStep === 3 ? "active" : ""}`}>
          <div className="step-circle">{isStep3Done ? "✓" : "3"}</div>
          <span className="step-label">Initial Analysis</span>
        </div>
        <div className={`step-item ${isStep4Done ? "completed" : currentStep === 4 ? "active" : ""}`}>
          <div className="step-circle">{isStep4Done ? "✓" : "4"}</div>
          <span className="step-label">Resolve Ambiguities</span>
        </div>
        <div className={`step-item ${isStep5Done ? "completed" : currentStep === 5 ? "active" : ""}`}>
          <div className="step-circle">{isStep5Done ? "✓" : "5"}</div>
          <span className="step-label">Final Spec & Agent</span>
        </div>
      </div>
    </>
  );
}
