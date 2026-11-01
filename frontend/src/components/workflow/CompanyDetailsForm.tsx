import type { WorkflowPageProps } from "./WorkflowPage";
import styles from "./CompanyDetailsForm.module.css";

type CompanyDetailsFormProps = Pick<WorkflowPageProps, "isStep1Done" | "handleSaveCompanyDetails" | "companyDetails" | "setCompanyDetails">;

export default function CompanyDetailsForm({
    isStep1Done,
    handleSaveCompanyDetails,
    companyDetails,
    setCompanyDetails,
}: CompanyDetailsFormProps) {
  return (
    <>
      <div className={`${styles.companyDetailsForm} card`}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "16px" }}>
                  <h3 style={{ margin: 0, fontSize: "1.1rem" }}>Step 1: Company & Project Details</h3>
                  {isStep1Done && <span className="status-pill status-ready">✓ Saved</span>}
                </div>
                <form onSubmit={handleSaveCompanyDetails} className="form-grid">
                  <div className="form-group">
                    <label>Company Name *</label>
                    <input
                      type="text"
                      className="input-text"
                      value={companyDetails.companyName}
                      onChange={(e) => setCompanyDetails({ ...companyDetails, companyName: e.target.value })}
                      placeholder="e.g. Acme Corp"
                      required
                    />
                  </div>
                  <div className="form-group">
                    <label>Department / Team</label>
                    <input
                      type="text"
                      className="input-text"
                      value={companyDetails.department}
                      onChange={(e) => setCompanyDetails({ ...companyDetails, department: e.target.value })}
                      placeholder="e.g. Engineering"
                    />
                  </div>
                  <div className="form-group">
                    <label>Project / Hiring Campaign</label>
                    <input
                      type="text"
                      className="input-text"
                      value={companyDetails.projectName}
                      onChange={(e) => setCompanyDetails({ ...companyDetails, projectName: e.target.value })}
                      placeholder="e.g. Q3 Hiring Drive"
                    />
                  </div>
                  <div style={{ gridColumn: "1 / -1", display: "flex", justifyContent: "flex-end" }}>
                    <button type="submit" className="btn-primary">
                      Save & Continue to JD →
                    </button>
                  </div>
                </form>
              </div>
    </>
  );
}
