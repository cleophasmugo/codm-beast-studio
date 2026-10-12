import { FolderOpen, ListChecks } from "lucide-react";
import { api, type Job } from "../api";
import { formatSeconds } from "../lib/format";
import { useAsync } from "../lib/hooks";
import { navigate } from "../lib/router";
import { ExportPlayer } from "./ExportPlayer";
import { Button, ErrorBanner, Spinner } from "./ui";

/** Shows what a finished job produced: the rendered video, download, and timeline notes. */
export function JobResult({ job }: { job: Job }) {
  const exportId = job.result?.export_id;
  const ex = useAsync(() => (exportId ? api.getExport(exportId) : Promise.resolve(null)), [exportId]);
  const notes = job.result?.notes ?? [];
  return (
    <div className="space-y-4" data-testid="job-result">
      {exportId ? (
        ex.loading && !ex.data ? (
          <Spinner label="Loading video" />
        ) : ex.error ? (
          <ErrorBanner onRetry={ex.reload}>{ex.error}</ErrorBanner>
        ) : ex.data ? (
          <ExportPlayer item={ex.data} showProjectLink={false} />
        ) : null
      ) : (
        <p className="text-sm text-ink-300">The timeline is ready (no video was rendered for this job).</p>
      )}
      <div className="rounded-xl border border-white/[0.08] bg-ink-900/60 p-3.5">
        <h3 className="mb-2 flex items-center gap-2 text-xs font-bold tracking-wide text-ink-200 uppercase">
          <ListChecks className="size-4 text-cyber" aria-hidden /> Timeline notes
        </h3>
        <ul className="space-y-1 text-sm text-ink-200">
          {job.result?.clip_count !== undefined && (
            <li>
              {job.result.clip_count} clips, {formatSeconds(job.result.duration ?? 0)} total.
            </li>
          )}
          {notes.map((n, i) => (
            <li key={i} className="text-ink-300">
              • {n}
            </li>
          ))}
          {!notes.length && <li className="text-ink-400">No warnings. The editor found enough action for the target length.</li>}
        </ul>
      </div>
      {job.project_id && (
        <Button variant="secondary" icon={<FolderOpen className="size-4" />} onClick={() => navigate(`/projects/${job.project_id}`)}>
          Fine-tune in the project editor
        </Button>
      )}
    </div>
  );
}
