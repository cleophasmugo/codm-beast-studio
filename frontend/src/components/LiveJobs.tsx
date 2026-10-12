import { Activity } from "lucide-react";
import { useState } from "react";
import { api, isActive, type Job } from "../api";
import { timeAgo } from "../lib/format";
import { useAsync, useInterval } from "../lib/hooks";
import { navigate } from "../lib/router";
import { JobProgressView, JobStatusBadge, jobLabel } from "./JobProgressCard";
import { Card, CardTitle } from "./ui";

/** Running jobs, refreshed live, plus the last few finished ones. */
export function LiveJobs({ projectNames }: { projectNames: Record<string, string> }) {
  const jobs = useAsync(() => api.listJobs(undefined, 12), []);
  const [busy, setBusy] = useState<string | null>(null);
  const running = (jobs.data ?? []).filter(isActive);
  useInterval(jobs.reload, running.length ? 1000 : 5000);

  const act = async (j: Job, fn: (id: string) => Promise<Job>) => {
    setBusy(j.id);
    try {
      await fn(j.id);
    } catch {
      /* the next poll shows the real state */
    } finally {
      setBusy(null);
      jobs.reload();
    }
  };

  const recent = (jobs.data ?? []).filter((j) => !isActive(j)).slice(0, 4);
  return (
    <Card>
      <CardTitle icon={<Activity className="size-4" />}>Live renders</CardTitle>
      {running.length === 0 ? (
        <p className="text-sm text-ink-400">Nothing rendering right now.</p>
      ) : (
        <div className="space-y-3">
          {running.map((j) => (
            <JobProgressView
              key={j.id}
              job={j}
              title={`${jobLabel(j.kind)}${j.project_id && projectNames[j.project_id] ? ` · ${projectNames[j.project_id]}` : ""}`}
              busy={busy === j.id}
              onCancel={() => act(j, api.cancelJob)}
            />
          ))}
        </div>
      )}
      {recent.length > 0 && (
        <ul className="mt-4 divide-y divide-white/5 border-t border-white/5">
          {recent.map((j) => (
            <li key={j.id} className="flex items-center gap-2 py-2 text-sm">
              <button
                type="button"
                className="min-w-0 flex-1 truncate text-left text-ink-200 hover:text-white"
                onClick={() => j.project_id && navigate(`/projects/${j.project_id}`)}
              >
                {jobLabel(j.kind)}
                {j.project_id && projectNames[j.project_id] ? ` · ${projectNames[j.project_id]}` : ""}
              </button>
              <span className="shrink-0 text-xs text-ink-400">{timeAgo(j.finished_at ?? j.created_at)}</span>
              <JobStatusBadge status={j.status} />
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
