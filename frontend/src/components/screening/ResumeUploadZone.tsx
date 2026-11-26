import { useRef, useCallback } from "react";
import styles from "./ResumeUploadZone.module.css";
import type { BatchResumeUploadResponse } from "@/lib/screening_api";

interface ResumeUploadZoneProps {
  isUploading: boolean;
  isScreening: boolean;
  uploadResult: BatchResumeUploadResponse | null;
  hasResumes: boolean;
  specFinalized: boolean;
  specificationVersion: number | null;
  onUpload: (files: File[]) => Promise<void>;
  onScreenAll: () => Promise<void>;
}

export default function ResumeUploadZone({
  isUploading, isScreening, uploadResult, hasResumes, specFinalized, specificationVersion, onUpload, onScreenAll,
}: ResumeUploadZoneProps) {
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    const files = Array.from(e.dataTransfer.files).filter((f) =>
      [".pdf", ".docx", ".txt"].some((ext) => f.name.toLowerCase().endsWith(ext))
    );
    if (files.length > 0) onUpload(files);
  }, [onUpload]);

  const handleFileChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files ?? []);
    if (files.length > 0) onUpload(files);
    if (fileInputRef.current) fileInputRef.current.value = "";
  }, [onUpload]);

  return (
    <div className={styles.uploadCard}>
      {/* Drop zone */}
      <div
        className={`${styles.dropZone} ${isUploading ? styles.uploading : ""}`}
        onDrop={handleDrop}
        onDragOver={(e) => e.preventDefault()}
        onClick={() => !isUploading && fileInputRef.current?.click()}
      >
        <input
          ref={fileInputRef}
          type="file"
          accept=".pdf,.docx,.txt"
          multiple
          className={styles.hiddenInput}
          onChange={handleFileChange}
          disabled={isUploading}
        />
        <div className={styles.dropZoneInner}>
          {isUploading ? (
            <>
              <span className={styles.spinner} />
              <span className={styles.dropLabel}>Uploading resumes…</span>
            </>
          ) : (
            <>
              <span className={styles.dropIcon}>📄</span>
              <span className={styles.dropLabel}>
                Drag &amp; drop resumes here, or <strong>click to browse</strong>
              </span>
              <span className={styles.dropHint}>Supports PDF, DOCX, TXT — multiple files at once</span>
            </>
          )}
        </div>
      </div>

      {/* Upload result feedback */}
      {uploadResult && (
        <div className={styles.uploadResult}>
          {uploadResult.uploaded.length > 0 && (
            <span className={styles.uploadSuccess}>
              ✅ {uploadResult.uploaded.length} resume{uploadResult.uploaded.length !== 1 ? "s" : ""} uploaded
            </span>
          )}
          {uploadResult.failed.length > 0 && (
            <span className={styles.uploadFail}>
              ❌ {uploadResult.failed.length} failed:{" "}
              {uploadResult.failed.map((f) => f.filename).join(", ")}
            </span>
          )}
        </div>
      )}

      {/* Screen all button */}
      {hasResumes && (
        <div className={styles.screenActions}>
          <button
            className={styles.screenBtn}
            onClick={onScreenAll}
            disabled={isScreening || isUploading || !specFinalized}
          >
            {isScreening ? (
              <><span className={styles.spinner} /> Triggering evaluation…</>
            ) : (
              <>🔍 Evaluate All Candidates</>
            )}
          </button>
          <span className={styles.screenHint}>
            {specFinalized ? `Evaluates resumes against finalized specification v${specificationVersion}.` : "Finalize the current job specification to enable screening."}
          </span>
        </div>
      )}
    </div>
  );
}
