import { motion } from "framer-motion";
import { AlertTriangle, CheckCircle2, Loader2, RotateCcw, Square, XCircle } from "lucide-react";
import { useState } from "react";
import { api, isActive, type Job } from "../api";
import { formatEta, titleCase } from "../lib/format";
import { useJob } from "../lib/hooks";
import { Badge, Button, ErrorBanner, ProgressBar, cx } from "./ui";

export function jobLabel(kind: string): string {
  return { auto_edit: "Auto Edit", render: "Render", analyze: "Analysis" }[kind] ?? titleCase(kind);
}

export function JobStatusBadge({ status }: { status: Job["status"] }) {
  const tone = { queued: "default", running: "cyan", done: "green", failed: "red", cancelled: "amber" } as const;
  return <Badge tone={tone[status] ?? "default"}>{titleCase(status)}</Badge>;
}

/** Presentational card for one job (no polling). */
export function JobProgressView({
  job,
  title,
  onCancel,
  onRetry,
  busy,
  pollError,
}: {
  job: Job;
  title?: string;
  onCancel?: () => void;
  onRetry?: () => void;
  busy?: boolean;
  pollError?: string | null;
}) {
  const active = isActive(job);
  const icon = active ? (
    <Loader2 className="size-5 animate-spin text-cyber" aria-hidden />
  ) : job.status === "done" ? (
    <CheckCircle2 className="size-5 text-toxic" aria-hidden />
  ) : job.status === "failed" ? (
    <XCircle className="size-5 text-rose-400" aria-hidden />
  ) : (
    <AlertTriangle className="size-5 text-amber-300" aria-hidden />
  );
  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      className={cx(
        "rounded-xl border bg-ink-900/70 p-4",
        active ? "border-cyber/30" : job.status === "done" ? "border-lime-400/30" : job.status === "failed" ? "border-rose-500/40" : "border-amber-400/30",
      )}
      data-testid="job-card"
      aria-live="polite"
    >
      <div className="flex items-start gap-3">
        <span className="mt-0.5">{icon}</span>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-bold text-white">{title ?? jobLabel(job.kind)}</span>
            <JobStatusBadge status={job.status} />
            {job.attempts > 1 && <Badge>attempt {job.attempts}</Badge>}
          </div>
          <p className="mt-0.5 text-sm text-ink-300">
            <span className="font-semibold text-ink-100">{job.stage || (job.status === "queued" ? "Queued" : "Working")}</span>
            {job.message && <span> · {job.message}</span>}
          </p>
        </div>
        <span className="shrink-0 font-mono text-sm font-bold text-cyber">{Math.round(job.progress * 100)}%</span>
      </div>
      <div className="mt-3">
        <ProgressBar
          value={job.progress}
          tone={job.status === "failed" ? "red" : job.status === "done" ? "green" : "brand"}
          label={`${jobLabel(job.kind)} progress`}
        />
      </div>
      <div className="mt-3 flex flex-wrap items-center justify-between gap-2">
        <span className="text-xs text-ink-400">{active ? formatEta(job.eta_seconds) : job.status === "done" ? "Finished" : ""}</span>
        <div className="flex gap-2">
          {active && onCancel && (
            <Button size="sm" variant="danger" onClick={onCancel} loading={busy} icon={<Square className="size-3.5" />}>
              Cancel
            </Button>
          )}
          {(job.status === "failed" || job.status === "cancelled") && onRetry && (
            <Button size="sm" variant="secondary" onClick={onRetry} loading={busy} icon={<RotateCcw className="size-3.5" />}>
              Retry
            </Button>
          )}
        </div>
      </div>
      {job.status === "failed" && job.error && (
        <div className="mt-3">
          <ErrorBanner>{job.error}</ErrorBanner>
        </div>
      )}
      {pollError && (
        <p className="mt-2 text-xs text-amber-300">Lost contact with the server ({pollError}). Still retrying…</p>
      )}
    </motion.div>
  );
}

/** Polls GET /api/jobs/{id} every second and offers Cancel / Retry. */
export function JobProgressCard({
  jobId,
  title,
  onFinish,
}: {
  jobId: string;
  title?: string;
  onFinish?: (job: Job) => void;
}) {
  const { job, error, restart } = useJob(jobId, onFinish);
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  if (!job) {
    return (
      <div className="flex items-center gap-2 rounded-xl border border-white/10 bg-ink-900/70 p-4 text-sm text-ink-300">
        <Loader2 className="size-4 animate-spin text-cyber" aria-hidden /> Starting job…
        {error && <span className="text-rose-300">{error}</span>}
      </div>
    );
  }
  const act = async (fn: () => Promise<Job>) => {
    setBusy(true);
    setActionError(null);
    try {
      const j = await fn();
      restart(j);
    } catch (e) {
      setActionError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="space-y-2">
      <JobProgressView
        job={job}
        title={title}
        busy={busy}
        pollError={error}
        onCancel={() => act(() => api.cancelJob(job.id))}
        onRetry={() => act(() => api.retryJob(job.id))}
      />
      {actionError && <ErrorBanner>{actionError}</ErrorBanner>}
    </div>
  );
}
