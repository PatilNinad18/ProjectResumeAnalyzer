import { useRef, useState, type FormEvent } from "react";
import type { SavedJD } from "@/lib/api";
import { triggerScreening, uploadCandidateResumes } from "@/lib/screening_api";
import styles from "./ScreeningPage.module.css";

interface BatchScreeningProps {
  jobs: SavedJD[];
  initialJobIds: string[];
  onViewJob: (jdId: string) => void;
  onRequestsFinished: () => void;
}

interface JobResult {
  queuedCount?: number;
  uploadErrors: string[];
  error?: string;
}

export default function BatchScreening({ jobs, initialJobIds, onViewJob, onRequestsFinished }: BatchScreeningProps) {
  const [isOpen, setIsOpen] = useState(initialJobIds.length > 1);
  const [checkedIds, setCheckedIds] = useState(initialJobIds);
  const [files, setFiles] = useState<File[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [results, setResults] = useState<Record<string, JobResult>>({});
  const fileInput = useRef<HTMLInputElement>(null);
  const selectedJobs = jobs.filter((job) => checkedIds.includes(job.jd_id));

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (submitting || selectedJobs.length === 0) return;
    setSubmitting(true);
    setResults({});

    try {
      for (const job of selectedJobs) {
        const result: JobResult = { uploadErrors: [] };
        try {
          let resumeIds: string[] | undefined;
          if (files.length > 0) {
            const uploaded = await uploadCandidateResumes(job.jd_id, files);
            resumeIds = uploaded.uploaded.map((item) => item.candidate_resume_id);
            for (const file of uploaded.failed) {
              if (file.existing_candidate_resume_id) resumeIds.push(file.existing_candidate_resume_id);
              else result.uploadErrors.push(`${file.filename} · ${file.error}`);
            }
            if (!resumeIds.length) throw new Error("No resumes from this upload could be queued.");
          }
          const response = await triggerScreening(job.jd_id, job.spec_version_id ?? undefined, resumeIds);
          result.queuedCount = response.queued_count;
        } catch (cause) {
          result.error = cause instanceof Error ? cause.message : "Could not queue this job.";
        }
        setResults((current) => ({ ...current, [job.jd_id]: result }));
      }
    } finally {
      setSubmitting(false);
      onRequestsFinished();
    }
  }

  return (
    <details className={styles.criticalPolicy} open={isOpen} onToggle={(event) => setIsOpen(event.currentTarget.open)}>
      <summary>Screen multiple jobs</summary>
      <form onSubmit={(event) => void submit(event)}>
        <p>Choose the finalized jobs to screen in this run.</p>
        <div className={styles.criticalOptions} role="group" aria-label="Jobs to screen">
          {jobs.map((job) => (
            <label key={job.jd_id}>
              <input
                type="checkbox"
                checked={checkedIds.includes(job.jd_id)}
                disabled={submitting}
                onChange={(event) => {
                  const checked = event.currentTarget.checked;
                  setCheckedIds((ids) => checked ? [...ids, job.jd_id] : ids.filter((id) => id !== job.jd_id));
                }}
              />
              {job.title} · {job.project_id}
            </label>
          ))}
        </div>
        <label className={styles.batchFileInput}>
          Use the same resume files for each selected job (optional)
          <input
            ref={fileInput}
            type="file"
            accept=".pdf,.docx,.txt"
            multiple
            disabled={submitting}
            onChange={(event) => setFiles(Array.from(event.currentTarget.files ?? []))}
          />
        </label>
        <p>{files.length > 0
          ? `${files.length} selected ${files.length === 1 ? "file will" : "files will"} be uploaded and screened for each checked job.`
          : "With no files selected, each checked job uses the resumes already uploaded to it."}</p>
        {files.length > 0 && (
          <button type="button" className="btn-secondary" disabled={submitting} onClick={() => {
            if (fileInput.current) fileInput.current.value = "";
            setFiles([]);
          }}>Clear files</button>
        )}{" "}
        <button type="submit" className="btn-primary" disabled={submitting || selectedJobs.length === 0}>
          {submitting ? "Queuing jobs…" : "Screen selected jobs"}
        </button>
      </form>
      <div aria-live="polite">
        {Object.keys(results).length > 0 && (
          <ul className={styles.batchResults}>
            {jobs.filter((job) => results[job.jd_id]).map((job) => {
              const result = results[job.jd_id];
              return (
                <li key={job.jd_id}>
                  <strong>{job.title}</strong>
                  <span>{result.error || `Queued ${result.queuedCount} candidate evaluation${result.queuedCount === 1 ? "" : "s"}.`}</span>
                  {result.uploadErrors.map((error, index) => <span key={index}>{error}</span>)}
                  <button type="button" className={styles.policyButton} onClick={() => onViewJob(job.jd_id)}>View {job.title}</button>
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </details>
  );
}
