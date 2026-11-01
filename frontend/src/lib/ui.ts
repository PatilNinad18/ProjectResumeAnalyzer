import type { ProcessingStatus } from "@/lib/api";

export const statusConfig: Record<
  ProcessingStatus,
  { label: string; icon: string; className: string }
> = {
  UPLOADED: { label: "Uploaded", icon: "↑", className: "status-uploaded" },
  PARSING: { label: "Parsing JD", icon: "◌", className: "status-processing" },
  UNDERSTANDING: { label: "Understanding JD", icon: "◌", className: "status-processing" },
  VALIDATING: { label: "Validating", icon: "◌", className: "status-processing" },
  GENERATING: { label: "Generating Context", icon: "◌", className: "status-processing" },
  READY: { label: "Analysis Ready", icon: "✓", className: "status-ready" },
  NEEDS_REVIEW: { label: "Needs Review", icon: "!", className: "status-review" },
  FAILED: { label: "Failed", icon: "×", className: "status-failed" },
};

export function formatElapsed(ms: number): string {
  const total = Math.max(0, Math.floor(ms / 1000));
  const minutes = Math.floor(total / 60);
  const seconds = total % 60;
  return `${minutes}:${seconds.toString().padStart(2, "0")}`;
}
