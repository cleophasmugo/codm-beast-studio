import { motion } from "framer-motion";
import { Clapperboard, FolderOpen, HardDrive, History, Rocket, Sparkles, Upload, X } from "lucide-react";
import { useCallback, useMemo, useState } from "react";
import { api, mediaUrl, type ExportItem, type Job, type Media, type PresetName } from "../api";
import { DurationPicker, durationToSeconds, type DurationChoice } from "../components/DurationPicker";
import { DownloadLink } from "../components/ExportPlayer";
import { JobProgressCard } from "../components/JobProgressCard";
import { JobResult } from "../components/JobResult";
import { LiveJobs } from "../components/LiveJobs";
import { MediaPicker } from "../components/MediaPicker";
import { PresetPicker } from "../components/PresetPicker";
import { useToast } from "../components/Toast";
import { UploadZone } from "../components/UploadZone";
import { Badge, Button, Card, CardTitle, Empty, ErrorBanner, Spinner, Stat } from "../components/ui";
import { formatBytes, formatDuration, timeAgo, titleCase } from "../lib/format";
import { useAsync, type AsyncState } from "../lib/hooks";
import { navigate } from "../lib/router";
import { readPref, writePref } from "../lib/token";

export function Dashboard() {
  const toast = useToast();
  const presets = useAsync(() => api.presets(), []);
  const media = useAsync(() => api.listMedia(), []);
  const projects = useAsync(() => api.listProjects(), []);
  const exports = useAsync(() => api.listExports(), []);
  const system = useAsync(() => api.system(), []);

  const [selected, setSelected] = useState<string[]>([]);
  const [preset, setPreset] = useState<PresetName>(() => readPref<PresetName>("quickPreset", "beast"));
  const [duration, setDuration] = useState<DurationChoice>(() => readPref<DurationChoice>("quickDuration", "30"));
  const [jobId, setJobId] = useState<string | null>(null);
  const [finished, setFinished] = useState<Job | null>(null);
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showAll, setShowAll] = useState(false);

  const usable = useMemo(
    () => (media.data ?? []).filter((m) => (m.kind === "video" || m.kind === "image") && m.source !== "library"),
    [media.data],
  );
  const projectNames = useMemo(
    () => Object.fromEntries((projects.data ?? []).map((p) => [p.id, p.name])),
    [projects.data],
  );

  const onUploaded = useCallback(
    (items: Media[]) => {
      media.setData((prev) => [...items, ...(prev ?? []).filter((m) => !items.some((i) => i.id === m.id))]);
      const ids = items.filter((m) => m.kind === "video" || m.kind === "image").map((m) => m.id);
      setSelected((s) => [...new Set([...s, ...ids])]);
      toast.success(`${items.length} file${items.length === 1 ? "" : "s"} uploaded`);
    },
    [media, toast],
  );

  const toggle = (id: string) => setSelected((s) => (s.includes(id) ? s.filter((x) => x !== id) : [...s, id]));

  const create = async () => {
    setError(null);
    setStarting(true);
    setFinished(null);
    try {
      const label = presets.data?.find((p) => p.id === preset)?.label ?? titleCase(preset);
      const job = await api.quickMontage({
        media_ids: selected,
        preset,
        target_duration: durationToSeconds(duration),
        name: `${label} montage`,
      });
      setJobId(job.id);
      writePref("quickPreset", preset);
      writePref("quickDuration", duration);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setStarting(false);
    }
  };

  const selectedMedia = usable.filter((m) => selected.includes(m.id));
  const visible = showAll ? usable : usable.slice(0, 8);

  return (
    <div className="space-y-6">
      <motion.section
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        className="panel glow-border relative overflow-hidden p-5 sm:p-7"
      >
        <div className="pointer-events-none absolute -top-24 -right-24 size-72 rounded-full bg-volt/20 blur-3xl" />
        <div className="pointer-events-none absolute -bottom-24 -left-24 size-72 rounded-full bg-cyber/15 blur-3xl" />
        <div className="relative">
          <Badge tone="green" className="mb-3">
            <Sparkles className="size-3" /> Automatic montage editor
          </Badge>
          <h1 className="font-display text-3xl font-extrabold tracking-tight text-white sm:text-4xl">
            Drop your gameplay. <span className="text-gradient">Get a beast montage.</span>
          </h1>
          <p className="mt-2 max-w-2xl text-sm text-ink-300 sm:text-base">
            Upload CODM clips and screenshots, pick a style, and Beast Studio finds the action, cuts it to the beat,
            grades it and renders a ready-to-post video.
          </p>
          <div className="mt-5">
            <UploadZone onUploaded={onUploaded} />
          </div>
        </div>
      </motion.section>

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_360px]">
        <div className="min-w-0 space-y-6">
          <Card>
            <CardTitle
              icon={<Rocket className="size-4" />}
              action={<span className="text-xs text-ink-400">{selected.length} selected</span>}
            >
              One-click montage
            </CardTitle>

            <div className="space-y-5">
              <div>
                <p className="label">1. Footage</p>
                {media.loading && !media.data ? (
                  <Spinner label="Loading your uploads" />
                ) : media.error ? (
                  <ErrorBanner onRetry={media.reload}>{media.error}</ErrorBanner>
                ) : (
                  <>
                    <MediaPicker
                      media={visible}
                      selected={selected}
                      onToggle={toggle}
                      emptyText="Upload gameplay videos or screenshots above to get started."
                    />
                    {usable.length > 8 && (
                      <Button size="sm" variant="ghost" className="mt-2" onClick={() => setShowAll((v) => !v)}>
                        {showAll ? "Show fewer" : `Show all ${usable.length}`}
                      </Button>
                    )}
                  </>
                )}
                {selectedMedia.length > 0 && (
                  <div className="mt-3 flex flex-wrap gap-1.5">
                    {selectedMedia.map((m) => (
                      <span key={m.id} className="inline-flex items-center gap-1 rounded-full border border-toxic/30 bg-toxic/10 py-0.5 pr-1 pl-2.5 text-xs text-lime-200">
                        {m.name}
                        <button type="button" aria-label={`Remove ${m.name}`} onClick={() => toggle(m.id)} className="rounded-full p-0.5 hover:bg-white/10">
                          <X className="size-3" />
                        </button>
                      </span>
                    ))}
                  </div>
                )}
              </div>

              <div>
                <p className="label">2. Style</p>
                {presets.data ? (
                  <PresetPicker presets={presets.data} value={preset} onChange={setPreset} compact />
                ) : presets.error ? (
                  <ErrorBanner onRetry={presets.reload}>{presets.error}</ErrorBanner>
                ) : (
                  <Spinner label="Loading presets" />
                )}
              </div>

              <DurationPicker value={duration} onChange={setDuration} />

              <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
                <Button
                  variant="primary"
                  size="lg"
                  onClick={create}
                  loading={starting}
                  disabled={!selected.length}
                  icon={<Clapperboard className="size-5" />}
                  data-testid="create-montage"
                >
                  Create My Montage
                </Button>
                <p className="text-xs text-ink-400">
                  {selected.length
                    ? "Uses a matching royalty-free library track. Change music and more in Auto Edit."
                    : "Select at least one video or screenshot."}
                </p>
              </div>
              {error && <ErrorBanner>{error}</ErrorBanner>}
              {jobId && (
                <div className="space-y-4">
                  <JobProgressCard
                    key={jobId}
                    jobId={jobId}
                    title="Creating your montage"
                    onFinish={(j) => {
                      if (j.status === "done") {
                        setFinished(j);
                        toast.success("Montage rendered");
                        exports.reload();
                        projects.reload();
                      }
                    }}
                  />
                  {finished && finished.id === jobId && <JobResult job={finished} />}
                </div>
              )}
            </div>
          </Card>

          <RecentExports exports={exports} />
        </div>

        <div className="min-w-0 space-y-6">
          <LiveJobs projectNames={projectNames} />

          <Card>
            <CardTitle
              icon={<FolderOpen className="size-4" />}
              action={
                <Button size="sm" variant="ghost" onClick={() => navigate("/projects")}>
                  All
                </Button>
              }
            >
              Recent projects
            </CardTitle>
            {projects.loading && !projects.data ? (
              <Spinner />
            ) : projects.error ? (
              <ErrorBanner onRetry={projects.reload}>{projects.error}</ErrorBanner>
            ) : !projects.data?.length ? (
              <p className="text-sm text-ink-400">No projects yet.</p>
            ) : (
              <ul className="space-y-2">
                {projects.data.slice(0, 5).map((p) => (
                  <li key={p.id}>
                    <button
                      type="button"
                      onClick={() => navigate(`/projects/${p.id}`)}
                      className="flex w-full items-center gap-3 rounded-xl border border-white/[0.06] bg-ink-900/50 p-2 text-left transition hover:border-cyber/40"
                    >
                      <div className="aspect-video w-20 shrink-0 overflow-hidden rounded-md bg-ink-800">
                        {p.latest_export?.thumb_url && (
                          <img src={mediaUrl(p.latest_export.thumb_url)} alt="" className="size-full object-cover" loading="lazy" />
                        )}
                      </div>
                      <div className="min-w-0 flex-1">
                        <div className="truncate text-sm font-semibold text-white">{p.name}</div>
                        <div className="text-xs text-ink-400">
                          {titleCase(p.settings.preset)} · {timeAgo(p.updated_at)}
                        </div>
                      </div>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </Card>

          <Card>
            <CardTitle icon={<HardDrive className="size-4" />}>Storage</CardTitle>
            {system.data ? (
              <div className="space-y-3">
                <Stat label="Total used" value={formatBytes(system.data.storage.total_bytes)} hint={`Upload limit ${system.data.limits.max_upload_mb} MB per file`} />
                <StorageBars areas={system.data.storage.by_area} total={system.data.storage.total_bytes} />
              </div>
            ) : system.error ? (
              <ErrorBanner onRetry={system.reload}>{system.error}</ErrorBanner>
            ) : (
              <Spinner />
            )}
          </Card>
        </div>
      </div>
    </div>
  );
}

function StorageBars({ areas, total }: { areas: Record<string, number>; total: number }) {
  const entries = Object.entries(areas).sort((a, b) => b[1] - a[1]);
  const colors = ["bg-cyber", "bg-volt", "bg-toxic", "bg-electric", "bg-pink-400", "bg-amber-300", "bg-ink-400"];
  return (
    <div>
      <div className="flex h-2.5 overflow-hidden rounded-full bg-ink-700" aria-hidden>
        {entries.map(([k, v], i) => (
          <div key={k} className={colors[i % colors.length]} style={{ width: `${total ? (v / total) * 100 : 0}%` }} />
        ))}
      </div>
      <ul className="mt-3 grid grid-cols-2 gap-x-3 gap-y-1 text-xs">
        {entries.map(([k, v], i) => (
          <li key={k} className="flex items-center gap-1.5 text-ink-300">
            <span className={`size-2 rounded-full ${colors[i % colors.length]}`} aria-hidden />
            <span className="flex-1 truncate">{titleCase(k)}</span>
            <span className="font-mono text-ink-200">{formatBytes(v)}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function RecentExports({ exports }: { exports: AsyncState<ExportItem[]> }) {
  return (
    <Card>
      <CardTitle
        icon={<History className="size-4" />}
        action={
          <Button size="sm" variant="ghost" onClick={() => navigate("/exports")}>
            All exports
          </Button>
        }
      >
        Recent exports
      </CardTitle>
      {exports.loading && !exports.data ? (
        <Spinner />
      ) : exports.error ? (
        <ErrorBanner onRetry={exports.reload}>{exports.error}</ErrorBanner>
      ) : !exports.data?.length ? (
        <Empty icon={<Upload className="size-7" />} title="No exports yet">
          Your finished montages and edited images show up here.
        </Empty>
      ) : (
        <ul className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {exports.data.slice(0, 6).map((e) => (
            <li key={e.id} className="overflow-hidden rounded-xl border border-white/[0.08] bg-ink-900/60">
              <button type="button" className="block w-full" onClick={() => navigate(`/exports?play=${e.id}`)} aria-label={`Play ${e.name}`}>
                <div className="aspect-video bg-black">
                  {e.thumb_url && <img src={mediaUrl(e.thumb_url)} alt="" className="size-full object-contain" loading="lazy" />}
                </div>
              </button>
              <div className="flex items-center gap-2 p-2.5">
                <div className="min-w-0 flex-1">
                  <div className="truncate text-xs font-semibold text-white">{e.name}</div>
                  <div className="text-[11px] text-ink-400">
                    {e.kind === "image" ? `${e.width}×${e.height}` : formatDuration(e.duration)} · {formatBytes(e.size_bytes)}
                  </div>
                </div>
                <DownloadLink item={e} size="sm" />
              </div>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
