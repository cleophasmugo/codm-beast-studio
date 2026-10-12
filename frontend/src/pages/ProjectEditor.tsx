import { Reorder } from "framer-motion";
import {
  ArrowDown,
  ArrowLeft,
  ArrowUp,
  Clapperboard,
  Eye,
  Film,
  GripVertical,
  History,
  ImageIcon,
  Layers,
  Music,
  Plus,
  Redo2,
  RotateCcw,
  Save,
  Settings2,
  Sparkles,
  Trash2,
  Type,
  Undo2,
  Wand2,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useReducer, useState } from "react";
import {
  api,
  ASPECTS,
  clipOutputDuration,
  FORMATS,
  mediaUrl,
  MOTIONS,
  QUALITIES,
  RESOLUTIONS,
  TEXT_ANIMATIONS,
  timelineDuration,
  TRANSITIONS,
  type Clip,
  type HighlightCandidate,
  type Job,
  type Media,
  type Motion,
  type OutputFormat,
  type Overlay,
  type Project,
  type ProjectSettings,
  type TextAnimation,
  type Timeline,
  type Transition,
} from "../api";
import { ExportPlayer } from "../components/ExportPlayer";
import { JobProgressCard } from "../components/JobProgressCard";
import { useToast } from "../components/Toast";
import {
  Badge,
  Button,
  Card,
  CardTitle,
  ConfirmDialog,
  Empty,
  ErrorBanner,
  IconButton,
  Note,
  NumberField,
  Segmented,
  SelectField,
  Slider,
  Spinner,
  TextField,
  Toggle,
  cx,
} from "../components/ui";
import { formatDate, formatDuration, formatLabel, formatSeconds, titleCase, uid } from "../lib/format";
import { useAsync } from "../lib/hooks";
import { navigate } from "../lib/router";
import { historyReducer, initialHistory, moveItem } from "../lib/timelineHistory";

type Panel = "clips" | "overlays" | "music" | "highlights" | "history" | "export";

function newOverlay(type: Overlay["type"], at: number, media_id: string | null = null): Overlay {
  return {
    id: uid(),
    type,
    text: type === "counter" ? "HIGHLIGHT 1" : type === "text" ? "CLUTCH" : "",
    media_id,
    start: Number(at.toFixed(2)),
    end: Number((at + 2.5).toFixed(2)),
    x: 0.5,
    y: type === "sticker" ? 0.5 : 0.15,
    scale: 1,
    rotation: 0,
    opacity: 1,
    color: "#FFFFFF",
    outline: "#000000",
    animation: "pop",
    keyframes: [],
    layer: 0,
  };
}

function isTypingTarget(t: EventTarget | null): boolean {
  if (!(t instanceof HTMLElement)) return false;
  if (t.isContentEditable || t.tagName === "TEXTAREA") return true;
  return t.tagName === "INPUT" && ["text", "search", "url", "email", "password"].includes((t as HTMLInputElement).type);
}

export function ProjectEditor({ id }: { id: string }) {
  const toast = useToast();
  const proj = useAsync(() => api.getProject(id), [id]);
  const media = useAsync(() => api.listMedia(), []);
  const system = useAsync(() => api.system(), []);
  const [hist, dispatch] = useReducer(historyReducer, initialHistory);
  const [settings, setSettings] = useState<ProjectSettings | null>(null);
  const [settingsDirty, setSettingsDirty] = useState(false);
  const [panel, setPanel] = useState<Panel>("clips");
  const [selectedClip, setSelectedClip] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [jobId, setJobId] = useState<string | null>(null);
  const [jobTitle, setJobTitle] = useState("Render");
  const [jobActive, setJobActive] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [confirmRerun, setConfirmRerun] = useState(false);
  const [revTick, setRevTick] = useState(0);

  const project = proj.data;
  const tl = hist.present;

  // load project -> history + settings
  useEffect(() => {
    if (!project) return;
    dispatch({ type: "load", timeline: project.timeline });
    setSettings(project.settings);
    setSettingsDirty(false);
  }, [project]);

  // resume polling a job that is already running for this project
  useEffect(() => {
    let alive = true;
    api
      .listJobs(id, 1)
      .then((jobs) => {
        const j = jobs[0];
        if (alive && j && (j.status === "queued" || j.status === "running")) {
          setJobId(j.id);
          setJobTitle(j.kind === "auto_edit" ? "Auto Edit" : "Render");
          setJobActive(true);
        }
      })
      .catch(() => {});
    return () => {
      alive = false;
    };
  }, [id]);

  const mediaById = useMemo(() => Object.fromEntries((media.data ?? []).map((m) => [m.id, m])), [media.data]);
  const edit = useCallback((update: (t: Timeline) => Timeline) => dispatch({ type: "edit", update }), []);
  const patchClip = useCallback(
    (cid: string, p: Partial<Clip>) => edit((t) => ({ ...t, clips: t.clips.map((c) => (c.id === cid ? { ...c, ...p } : c)) })),
    [edit],
  );

  // keyboard undo / redo
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (!(e.ctrlKey || e.metaKey) || isTypingTarget(e.target)) return;
      const k = e.key.toLowerCase();
      if (k === "z" && !e.shiftKey) {
        e.preventDefault();
        dispatch({ type: "undo" });
      } else if ((k === "z" && e.shiftKey) || k === "y") {
        e.preventDefault();
        dispatch({ type: "redo" });
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  // warn before leaving with unsaved edits
  useEffect(() => {
    if (!hist.dirty && !settingsDirty) return;
    const h = (e: BeforeUnloadEvent) => e.preventDefault();
    window.addEventListener("beforeunload", h);
    return () => window.removeEventListener("beforeunload", h);
  }, [hist.dirty, settingsDirty]);

  const saveAll = async (note = "Manual edit"): Promise<Project | null> => {
    if (!project) return null;
    setSaving(true);
    setError(null);
    try {
      let p: Project = project;
      if (settingsDirty && settings) {
        p = await api.updateProject(project.id, { settings });
        setSettingsDirty(false);
      }
      if (hist.dirty && tl) {
        p = await api.saveTimeline(project.id, tl, note);
        dispatch({ type: "saved" });
        setRevTick((t) => t + 1);
      }
      return p;
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      return null;
    } finally {
      setSaving(false);
    }
  };

  const startJob = async (kind: "preview" | "export" | "auto") => {
    setError(null);
    if (hist.dirty || settingsDirty) {
      const ok = await saveAll(kind === "auto" ? "Before Auto Edit" : "Before render");
      if (!ok) return;
    }
    try {
      const j =
        kind === "auto"
          ? await api.autoEdit(id, settings ?? undefined, true)
          : await api.render(id, kind === "preview");
      setJobTitle(kind === "auto" ? "Re-running Auto Edit" : kind === "preview" ? "Rendering preview" : "Exporting");
      setJobId(j.id);
      setJobActive(true);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  const onJobFinish = (j: Job) => {
    setJobActive(false);
    if (j.status === "done") {
      toast.success(j.kind === "auto_edit" ? "Auto Edit finished" : "Render finished");
      proj.reload();
      setRevTick((t) => t + 1);
    }
  };

  const rename = async (name: string) => {
    if (!project || !name.trim() || name === project.name) return;
    try {
      const p = await api.updateProject(project.id, { name: name.trim() });
      proj.setData((prev) => (prev ? { ...prev, name: p.name } : p));
      toast.success("Renamed");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : String(e));
    }
  };

  if (proj.loading && !project) return <Spinner label="Loading project" />;
  if (proj.error && !project)
    return (
      <div className="space-y-4">
        <ErrorBanner onRetry={proj.reload}>{proj.error}</ErrorBanner>
        <Button onClick={() => navigate("/projects")} icon={<ArrowLeft className="size-4" />}>
          All projects
        </Button>
      </div>
    );
  if (!project || !settings) return null;

  const dirty = hist.dirty || settingsDirty;
  const total = tl ? timelineDuration(tl) : 0;
  const PANELS: [Panel, string, React.ReactNode][] = [
    ["clips", "Clips", <Film key="c" className="size-4" />],
    ["overlays", "Overlays", <Type key="o" className="size-4" />],
    ["music", "Music", <Music key="m" className="size-4" />],
    ["highlights", "Highlights", <Sparkles key="h" className="size-4" />],
    ["history", "History", <History key="r" className="size-4" />],
    ["export", "Output", <Settings2 key="e" className="size-4" />],
  ];

  return (
    <div className="space-y-5">
      {/* header */}
      <div className="flex flex-col gap-3 lg:flex-row lg:items-center">
        <div className="flex min-w-0 flex-1 items-center gap-2">
          <IconButton label="Back to projects" onClick={() => navigate("/projects")}>
            <ArrowLeft className="size-5" />
          </IconButton>
          <input
            aria-label="Project name"
            defaultValue={project.name}
            key={project.name}
            onBlur={(e) => void rename(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && (e.target as HTMLInputElement).blur()}
            className="min-w-0 flex-1 rounded-lg border border-transparent bg-transparent px-2 py-1 text-xl font-extrabold text-white hover:border-white/10 focus:border-cyber/50 focus:outline-none sm:text-2xl"
          />
          {dirty && <Badge tone="amber">Unsaved</Badge>}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <IconButton label="Undo (Ctrl+Z)" onClick={() => dispatch({ type: "undo" })} disabled={!hist.past.length}>
            <Undo2 className="size-4" />
          </IconButton>
          <IconButton label="Redo (Ctrl+Shift+Z)" onClick={() => dispatch({ type: "redo" })} disabled={!hist.future.length}>
            <Redo2 className="size-4" />
          </IconButton>
          <Button size="sm" variant="secondary" onClick={() => void saveAll()} disabled={!dirty} loading={saving} icon={<Save className="size-3.5" />} data-testid="save-timeline">
            Save
          </Button>
          <Button size="sm" variant="secondary" onClick={() => void startJob("preview")} disabled={!tl || jobActive} icon={<Eye className="size-3.5" />}>
            Render preview
          </Button>
          <Button size="sm" variant="primary" onClick={() => void startJob("export")} disabled={!tl || jobActive} icon={<Clapperboard className="size-3.5" />} data-testid="export-render">
            Export
          </Button>
          <Button size="sm" variant="ghost" onClick={() => setConfirmRerun(true)} disabled={jobActive} icon={<Wand2 className="size-3.5" />}>
            Re-run Auto Edit
          </Button>
        </div>
      </div>

      {error && <ErrorBanner>{error}</ErrorBanner>}

      <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_minmax(0,420px)]">
        {/* preview column */}
        <div className="min-w-0 space-y-4">
          <Card>
            {project.latest_export ? (
              <ExportPlayer item={project.latest_export} showProjectLink={false} />
            ) : (
              <Empty icon={<Clapperboard className="size-8" />} title="No render yet">
                {tl ? "Click Export or Render preview to make a video." : "Run Auto Edit to build the first timeline."}
              </Empty>
            )}
            {jobId && (
              <div className="mt-4">
                <JobProgressCard key={jobId} jobId={jobId} title={jobTitle} onFinish={onJobFinish} />
              </div>
            )}
          </Card>

          {tl ? (
            <TimelineStrip
              tl={tl}
              total={total}
              mediaById={mediaById}
              selected={selectedClip}
              onSelect={(cid) => {
                setSelectedClip(cid);
                setPanel("clips");
              }}
              onReorder={(clips) => edit((t) => ({ ...t, clips }))}
            />
          ) : (
            <Card>
              <Empty title="No timeline yet">
                <Button className="mt-3" variant="primary" onClick={() => void startJob("auto")} disabled={jobActive} icon={<Wand2 className="size-4" />}>
                  Run Auto Edit
                </Button>
              </Empty>
            </Card>
          )}
          {tl && tl.notes.length > 0 && (
            <Note>
              {tl.notes.map((n, i) => (
                <p key={i}>{n}</p>
              ))}
            </Note>
          )}
        </div>

        {/* side panels */}
        <div className="min-w-0 space-y-3">
          <div role="tablist" aria-label="Editor panels" className="grid grid-cols-3 gap-1 rounded-xl border border-white/[0.08] bg-ink-900/70 p-1">
            {PANELS.map(([pid, label, icon]) => (
              <button
                key={pid}
                type="button"
                role="tab"
                aria-selected={panel === pid}
                onClick={() => setPanel(pid)}
                title={label}
                className={cx(
                  "flex min-w-0 items-center justify-center gap-1.5 rounded-lg px-2 py-2 text-xs font-semibold transition",
                  panel === pid ? "bg-gradient-to-r from-cyber/25 to-volt/20 text-white" : "text-ink-300 hover:text-white",
                )}
              >
                {icon}
                <span className="truncate">{label}</span>
              </button>
            ))}
          </div>

          {panel === "clips" && tl && (
            <ClipsPanel
              tl={tl}
              mediaById={mediaById}
              selected={selectedClip}
              setSelected={setSelectedClip}
              patchClip={patchClip}
              edit={edit}
            />
          )}
          {panel === "overlays" && tl && <OverlaysPanel tl={tl} edit={edit} total={total} stickers={(media.data ?? []).filter((m) => m.kind === "sticker")} />}
          {panel === "music" && tl && <MusicPanel tl={tl} edit={edit} tracks={(media.data ?? []).filter((m) => m.kind === "audio")} />}
          {panel === "highlights" && (
            <HighlightsPanel projectId={id} mediaById={mediaById} canAdd={!!tl} onAdd={(c) => {
              const clip: Clip = {
                id: uid(), kind: "video", media_id: c.media_id, start: c.start, end: c.end, duration: 0, ramp: null,
                transition: "cut", punch_in: false, shake: false, motion: "none", crop_x: c.crop_x ?? null, text: "", subtitle: "",
                score: c.score, reasons: c.reasons, muted: false,
              };
              edit((t) => ({ ...t, clips: [...t.clips, clip] }));
              toast.success("Highlight added to the end of the timeline");
            }} />
          )}
          {panel === "history" && (
            <RevisionsPanel
              projectId={id}
              tick={revTick}
              onRestored={(p) => {
                proj.setData(p);
                toast.success("Revision restored");
              }}
            />
          )}
          {panel === "export" && (
            <ExportSettingsPanel
              settings={settings}
              formats={system.data?.formats}
              onChange={(s) => {
                setSettings(s);
                setSettingsDirty(true);
              }}
            />
          )}
          {!tl && (panel === "clips" || panel === "overlays" || panel === "music") && (
            <Card>
              <p className="text-sm text-ink-400">Run Auto Edit first to create a timeline you can edit.</p>
            </Card>
          )}
        </div>
      </div>

      <ConfirmDialog
        open={confirmRerun}
        title="Re-run Auto Edit?"
        confirmLabel="Re-run"
        message="This rebuilds the timeline from your footage with the current settings and renders it. Your current timeline is kept in History, so you can restore it."
        onCancel={() => setConfirmRerun(false)}
        onConfirm={() => {
          setConfirmRerun(false);
          void startJob("auto");
        }}
      />
    </div>
  );
}

// ----------------------------------------------------------------------------- timeline strip
function clipThumb(c: Clip, m: Media | undefined): string | null {
  if (!c.media_id) return null;
  if (c.kind === "video") return mediaUrl(api.frameUrl(c.media_id, c.start + Math.min(0.5, (c.end - c.start) / 2)));
  return m?.thumb_url ? mediaUrl(m.thumb_url) : mediaUrl(`/api/media/${c.media_id}/thumb`);
}

function TimelineStrip({
  tl,
  total,
  mediaById,
  selected,
  onSelect,
  onReorder,
}: {
  tl: Timeline;
  total: number;
  mediaById: Record<string, Media>;
  selected: string | null;
  onSelect: (id: string) => void;
  onReorder: (clips: Clip[]) => void;
}) {
  return (
    <Card>
      <CardTitle icon={<Layers className="size-4" />} action={<span className="font-mono text-xs text-cyber">{formatDuration(total)}</span>}>
        Clip sequence
      </CardTitle>
      {/* proportional bar */}
      <div className="mb-4 flex h-3 overflow-hidden rounded-full bg-ink-700" aria-hidden>
        {tl.clips.map((c, i) => (
          <div
            key={c.id}
            className={cx(
              "h-full border-r border-ink-950",
              c.id === selected ? "bg-toxic" : c.kind === "video" ? (i % 2 ? "bg-cyber/70" : "bg-electric/70") : c.kind === "image" ? "bg-volt/70" : "bg-pink-400/70",
            )}
            style={{ width: `${total ? (clipOutputDuration(c) / total) * 100 : 0}%` }}
          />
        ))}
      </div>
      {tl.clips.length === 0 ? (
        <p className="text-sm text-ink-400">The timeline is empty. Add highlights from the Highlights panel.</p>
      ) : (
        <Reorder.Group axis="x" values={tl.clips} onReorder={onReorder} className="flex gap-2 overflow-x-auto pb-2" data-testid="clip-strip">
          {tl.clips.map((c, i) => {
            const thumb = clipThumb(c, c.media_id ? mediaById[c.media_id] : undefined);
            return (
              <Reorder.Item key={c.id} value={c} className="w-32 shrink-0 cursor-grab active:cursor-grabbing" whileDrag={{ scale: 1.05, zIndex: 10 }}>
                <button
                  type="button"
                  onClick={() => onSelect(c.id)}
                  aria-pressed={selected === c.id}
                  aria-label={`Clip ${i + 1}, ${c.kind}, ${formatSeconds(clipOutputDuration(c))}`}
                  className={cx(
                    "block w-full overflow-hidden rounded-lg border text-left transition",
                    selected === c.id ? "border-toxic shadow-[0_0_16px_-4px_rgb(163_230_53/0.9)]" : "border-white/10 hover:border-white/30",
                  )}
                >
                  <div className="relative aspect-video bg-ink-800">
                    {thumb ? (
                      <img src={thumb} alt="" className="pointer-events-none size-full object-cover" loading="lazy" draggable={false} />
                    ) : (
                      <div className="grid size-full place-items-center bg-gradient-to-br from-volt/40 to-cyber/30 p-1 text-center text-[10px] font-bold text-white">
                        {c.text || "Card"}
                      </div>
                    )}
                    <span className="absolute top-1 left-1 rounded bg-black/75 px-1 font-mono text-[10px] text-white">{i + 1}</span>
                    <span className="absolute right-1 bottom-1 rounded bg-black/75 px-1 font-mono text-[10px] text-white">{formatSeconds(clipOutputDuration(c))}</span>
                    <GripVertical className="absolute top-1 right-1 size-3.5 text-white/70" aria-hidden />
                  </div>
                  <div className="flex items-center gap-1 bg-ink-900 px-1.5 py-1 text-[10px] text-ink-300">
                    {c.kind === "video" ? <Film className="size-3" aria-hidden /> : c.kind === "image" ? <ImageIcon className="size-3" aria-hidden /> : <Type className="size-3" aria-hidden />}
                    <span className="truncate">{titleCase(c.transition)}</span>
                    {c.ramp && <span className="ml-auto text-cyan-300">slow</span>}
                  </div>
                </button>
              </Reorder.Item>
            );
          })}
        </Reorder.Group>
      )}
      <p className="mt-1 text-[11px] text-ink-400">Drag clips to reorder, or use the arrows in the Clips panel. Ctrl+Z undoes, Ctrl+Shift+Z redoes.</p>
    </Card>
  );
}

// ----------------------------------------------------------------------------- clips panel
function ClipsPanel({
  tl,
  mediaById,
  selected,
  setSelected,
  patchClip,
  edit,
}: {
  tl: Timeline;
  mediaById: Record<string, Media>;
  selected: string | null;
  setSelected: (id: string | null) => void;
  patchClip: (id: string, p: Partial<Clip>) => void;
  edit: (fn: (t: Timeline) => Timeline) => void;
}) {
  const idx = tl.clips.findIndex((c) => c.id === selected);
  const c = idx >= 0 ? tl.clips[idx] : undefined;
  const m = c?.media_id ? mediaById[c.media_id] : undefined;
  const srcDur = m?.info.duration ?? (c ? c.end + 5 : 0);

  return (
    <Card>
      <ul className="max-h-64 space-y-1 overflow-y-auto pr-1">
        {tl.clips.map((cl, i) => (
          <li key={cl.id} className={cx("flex items-center gap-1 rounded-lg border px-2 py-1", cl.id === selected ? "border-toxic/60 bg-toxic/[0.06]" : "border-white/[0.06]")}>
            <button type="button" onClick={() => setSelected(cl.id)} className="flex min-w-0 flex-1 items-center gap-2 py-1 text-left text-sm">
              <span className="w-5 shrink-0 font-mono text-xs text-ink-400">{i + 1}</span>
              <span className="truncate text-ink-100">
                {cl.kind === "card" ? cl.text || "Title card" : (cl.media_id && mediaById[cl.media_id]?.name) || titleCase(cl.kind)}
              </span>
              <span className="ml-auto shrink-0 font-mono text-xs text-ink-300">{formatSeconds(clipOutputDuration(cl))}</span>
            </button>
            <IconButton label={`Move clip ${i + 1} up`} disabled={i === 0} onClick={() => edit((t) => ({ ...t, clips: moveItem(t.clips, i, i - 1) }))}>
              <ArrowUp className="size-4" />
            </IconButton>
            <IconButton label={`Move clip ${i + 1} down`} disabled={i === tl.clips.length - 1} onClick={() => edit((t) => ({ ...t, clips: moveItem(t.clips, i, i + 1) }))}>
              <ArrowDown className="size-4" />
            </IconButton>
          </li>
        ))}
      </ul>

      {!c ? (
        <p className="mt-4 text-sm text-ink-400">Select a clip to trim it, change its transition or effects.</p>
      ) : (
        <div className="mt-4 space-y-3 border-t border-white/5 pt-4" data-testid="clip-editor">
          <div className="flex items-center gap-2">
            <h3 className="flex-1 text-sm font-bold text-white">
              Clip {idx + 1} <span className="font-normal text-ink-400">· {titleCase(c.kind)}</span>
            </h3>
            <Button
              size="sm"
              variant="danger"
              icon={<Trash2 className="size-3.5" />}
              onClick={() => {
                edit((t) => ({ ...t, clips: t.clips.filter((x) => x.id !== c.id) }));
                setSelected(null);
              }}
            >
              Delete clip
            </Button>
          </div>
          {c.reasons.length > 0 && (
            <div className="flex flex-wrap gap-1">
              <Badge tone="green">score {c.score.toFixed(2)}</Badge>
              {c.reasons.map((r) => (
                <Badge key={r}>{r}</Badge>
              ))}
            </div>
          )}
          {c.kind === "video" ? (
            <>
              <div className="grid grid-cols-2 gap-3">
                <NumberField label="Start (s)" value={c.start} min={0} max={c.end - 0.1} step={0.1} onChange={(v) => patchClip(c.id, { start: Math.max(0, Math.min(v, c.end - 0.1)) })} />
                <NumberField label="End (s)" value={c.end} min={c.start + 0.1} max={srcDur} step={0.1} onChange={(v) => patchClip(c.id, { end: Math.min(srcDur, Math.max(v, c.start + 0.1)) })} />
              </div>
              <Slider label="In point" value={c.start} min={0} max={srcDur} step={0.05} format={(v) => `${v.toFixed(2)}s`} onChange={(v) => patchClip(c.id, { start: Math.min(v, c.end - 0.1) })} />
              <Slider label="Out point" value={c.end} min={0} max={srcDur} step={0.05} format={(v) => `${v.toFixed(2)}s`} onChange={(v) => patchClip(c.id, { end: Math.max(v, c.start + 0.1) })} />
              <div className="grid grid-cols-2 gap-x-4">
                <Toggle label="Punch-in" checked={c.punch_in} onChange={(v) => patchClip(c.id, { punch_in: v })} />
                <Toggle label="Shake" checked={c.shake} onChange={(v) => patchClip(c.id, { shake: v })} />
                <Toggle label="Mute game audio" checked={c.muted} onChange={(v) => patchClip(c.id, { muted: v })} />
                <Toggle label="Slow-mo ramp" checked={!!c.ramp} onChange={(v) => patchClip(c.id, { ramp: v ? { at: Math.max(0, (c.end - c.start) / 3), duration: Math.min(0.8, (c.end - c.start) / 2), speed: 0.5 } : null })} />
              </div>
            </>
          ) : (
            <>
              <NumberField label="Duration (s)" value={c.duration} min={0.5} max={10} step={0.1} onChange={(v) => patchClip(c.id, { duration: Math.min(10, Math.max(0.5, v)) })} />
              {c.kind === "image" && (
                <SelectField label="Motion" value={c.motion} onChange={(e) => patchClip(c.id, { motion: e.target.value as Motion })}>
                  {MOTIONS.map((mo) => (
                    <option key={mo} value={mo}>
                      {titleCase(mo)}
                    </option>
                  ))}
                </SelectField>
              )}
              {c.kind === "card" && (
                <>
                  <TextField label="Card title" value={c.text} onChange={(v) => patchClip(c.id, { text: v })} />
                  <TextField label="Card subtitle" value={c.subtitle} onChange={(v) => patchClip(c.id, { subtitle: v })} />
                </>
              )}
            </>
          )}
          <SelectField label="Transition into this clip" value={c.transition} onChange={(e) => patchClip(c.id, { transition: e.target.value as Transition })}>
            {TRANSITIONS.map((t) => (
              <option key={t} value={t}>
                {titleCase(t)}
              </option>
            ))}
          </SelectField>
        </div>
      )}
    </Card>
  );
}

// ----------------------------------------------------------------------------- overlays
function OverlaysPanel({ tl, edit, total, stickers }: { tl: Timeline; edit: (fn: (t: Timeline) => Timeline) => void; total: number; stickers: Media[] }) {
  const [sel, setSel] = useState<string | null>(null);
  const o = tl.overlays.find((x) => x.id === sel);
  const patch = (p: Partial<Overlay>) => o && edit((t) => ({ ...t, overlays: t.overlays.map((x) => (x.id === o.id ? { ...x, ...p } : x)) }));
  const add = (type: Overlay["type"]) => {
    const ov = newOverlay(type, 0, type === "sticker" ? (stickers[0]?.id ?? null) : null);
    edit((t) => ({ ...t, overlays: [...t.overlays, ov] }));
    setSel(ov.id);
  };
  return (
    <Card>
      <div className="flex flex-wrap gap-2">
        <Button size="sm" variant="secondary" icon={<Plus className="size-3.5" />} onClick={() => add("text")}>
          Text
        </Button>
        <Button size="sm" variant="secondary" icon={<Plus className="size-3.5" />} onClick={() => add("sticker")} disabled={!stickers.length}>
          Sticker
        </Button>
        <Button size="sm" variant="secondary" icon={<Plus className="size-3.5" />} onClick={() => add("counter")}>
          Counter
        </Button>
      </div>
      <ul className="mt-3 space-y-1">
        {tl.overlays.length === 0 && <li className="text-sm text-ink-400">No overlays.</li>}
        {tl.overlays.map((x) => (
          <li key={x.id} className={cx("flex items-center gap-1 rounded-lg border px-2 py-1", x.id === sel ? "border-cyber/60 bg-cyber/[0.06]" : "border-white/[0.06]")}>
            <button type="button" className="flex min-w-0 flex-1 items-center gap-2 py-1 text-left text-sm" onClick={() => setSel(x.id)}>
              <Badge tone={x.type === "text" ? "cyan" : x.type === "sticker" ? "violet" : "amber"}>{x.type}</Badge>
              <span className="truncate text-ink-100">{x.type === "sticker" ? (stickers.find((s) => s.id === x.media_id)?.name ?? "Sticker") : x.text}</span>
              <span className="ml-auto shrink-0 font-mono text-xs text-ink-400">
                {x.start.toFixed(1)}–{x.end.toFixed(1)}s
              </span>
            </button>
            <IconButton label="Delete overlay" className="hover:text-rose-400" onClick={() => edit((t) => ({ ...t, overlays: t.overlays.filter((y) => y.id !== x.id) }))}>
              <Trash2 className="size-4" />
            </IconButton>
          </li>
        ))}
      </ul>
      {o && (
        <div className="mt-4 space-y-2 border-t border-white/5 pt-4">
          {o.type === "sticker" ? (
            <SelectField label="Sticker" value={o.media_id ?? ""} onChange={(e) => patch({ media_id: e.target.value })}>
              {stickers.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                </option>
              ))}
            </SelectField>
          ) : (
            <TextField label="Text" value={o.text} onChange={(v) => patch({ text: v })} maxLength={120} />
          )}
          <div className="grid grid-cols-2 gap-3">
            <NumberField label="Start (s)" value={o.start} min={0} max={Math.max(0, total)} step={0.1} onChange={(v) => patch({ start: Math.max(0, Math.min(v, o.end - 0.1)) })} />
            <NumberField label="End (s)" value={o.end} min={o.start + 0.1} step={0.1} onChange={(v) => patch({ end: Math.max(v, o.start + 0.1) })} />
          </div>
          <Slider label="X position" value={o.x} min={0} max={1} onChange={(v) => patch({ x: v })} />
          <Slider label="Y position" value={o.y} min={0} max={1} onChange={(v) => patch({ y: v })} />
          <Slider label="Scale" value={o.scale} min={0.2} max={5} onChange={(v) => patch({ scale: v })} />
          <Slider label="Opacity" value={o.opacity} min={0} max={1} format={(v) => `${Math.round(v * 100)}%`} onChange={(v) => patch({ opacity: v })} />
          <SelectField label="Animation" value={o.animation} onChange={(e) => patch({ animation: e.target.value as TextAnimation })}>
            {TEXT_ANIMATIONS.map((a) => (
              <option key={a} value={a}>
                {titleCase(a)}
              </option>
            ))}
          </SelectField>
          {o.type !== "sticker" && (
            <div className="flex flex-wrap gap-4 pt-1">
              <label className="flex items-center gap-2 text-xs text-ink-200">
                Colour
                <input type="color" value={o.color} onChange={(e) => patch({ color: e.target.value.toUpperCase() })} className="h-8 w-10 rounded border border-white/10 bg-transparent" />
              </label>
              <label className="flex items-center gap-2 text-xs text-ink-200">
                Outline
                <input type="color" value={o.outline} onChange={(e) => patch({ outline: e.target.value.toUpperCase() })} className="h-8 w-10 rounded border border-white/10 bg-transparent" />
              </label>
            </div>
          )}
        </div>
      )}
    </Card>
  );
}

// ----------------------------------------------------------------------------- music
function MusicPanel({ tl, edit, tracks }: { tl: Timeline; edit: (fn: (t: Timeline) => Timeline) => void; tracks: Media[] }) {
  const mu = tl.music;
  const track = mu ? tracks.find((t) => t.id === mu.media_id) : undefined;
  const set = (p: Partial<NonNullable<Timeline["music"]>>) => mu && edit((t) => ({ ...t, music: { ...mu, ...p } }));
  return (
    <Card>
      <SelectField
        label="Track"
        value={mu?.media_id ?? ""}
        onChange={(e) =>
          edit((t) => ({
            ...t,
            music: e.target.value ? { media_id: e.target.value, offset: mu?.offset ?? 0, volume: mu?.volume ?? 0.8, fade_in: mu?.fade_in ?? 0.5, fade_out: mu?.fade_out ?? 1.5 } : null,
          }))
        }
      >
        <option value="">No music</option>
        {tracks.map((t) => (
          <option key={t.id} value={t.id}>
            {t.name}
          </option>
        ))}
      </SelectField>
      {mu && (
        <div className="mt-3 space-y-1">
          <Slider label="Song offset" value={mu.offset} min={0} max={Math.max(1, (track?.info.duration ?? 60) - 1)} step={0.1} format={(v) => `${v.toFixed(1)}s`} onChange={(v) => set({ offset: v })} />
          <Slider label="Volume" value={mu.volume} min={0} max={2} format={(v) => `${Math.round(v * 100)}%`} onChange={(v) => set({ volume: v })} />
          <Slider label="Fade in" value={mu.fade_in} min={0} max={10} step={0.1} format={(v) => `${v.toFixed(1)}s`} onChange={(v) => set({ fade_in: v })} />
          <Slider label="Fade out" value={mu.fade_out} min={0} max={10} step={0.1} format={(v) => `${v.toFixed(1)}s`} onChange={(v) => set({ fade_out: v })} />
          {tl.bpm && <p className="pt-1 text-xs text-ink-400">Detected tempo: {tl.bpm.toFixed(0)} BPM. Cuts were placed on beats when Auto Edit ran.</p>}
          {track && <audio controls preload="none" src={mediaUrl(track.url)} className="mt-2 h-9 w-full" aria-label={`Preview ${track.name}`} />}
        </div>
      )}
    </Card>
  );
}

// ----------------------------------------------------------------------------- highlights
function HighlightsPanel({ projectId, mediaById, canAdd, onAdd }: { projectId: string; mediaById: Record<string, Media>; canAdd: boolean; onAdd: (c: HighlightCandidate) => void }) {
  const h = useAsync(() => api.highlights(projectId), [projectId]);
  if (h.loading && !h.data) return <Spinner label="Loading highlights" />;
  if (h.error) return <Card><p className="text-sm text-ink-300">{h.error}</p></Card>;
  if (!h.data) return null;
  return (
    <Card>
      <Note tone="warn">{h.data.evidence_note}</Note>
      <div className="mt-3 max-h-[60vh] space-y-4 overflow-y-auto pr-1">
        {Object.entries(h.data.media).map(([mid, mh]) => (
          <div key={mid}>
            <h3 className="mb-2 text-xs font-bold tracking-wide text-ink-300 uppercase">
              {mediaById[mid]?.name ?? mh.name} · {mh.candidates.length} candidates
            </h3>
            <ul className="space-y-2">
              {mh.candidates.map((c, i) => (
                <li key={i} className="flex gap-2.5 rounded-xl border border-white/[0.07] bg-ink-900/60 p-2">
                  <img src={mediaUrl(api.frameUrl(c.media_id, c.peak))} alt="" className="aspect-video w-24 shrink-0 rounded-md bg-ink-800 object-cover" loading="lazy" />
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-1.5">
                      <span className="font-mono text-xs text-white">
                        {formatDuration(c.start)}–{formatDuration(c.end)}
                      </span>
                      <Badge tone={c.score > 0.8 ? "green" : c.score > 0.5 ? "cyan" : "default"}>score {c.score.toFixed(2)}</Badge>
                      <Badge tone="amber">{c.evidence}</Badge>
                    </div>
                    <p className="mt-1 text-[11px] leading-snug text-ink-300">{c.reasons.join(" · ") || "No specific signal"}</p>
                  </div>
                  <IconButton label="Add this highlight to the timeline" disabled={!canAdd} onClick={() => onAdd(c)}>
                    <Plus className="size-4" />
                  </IconButton>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>
    </Card>
  );
}

// ----------------------------------------------------------------------------- revisions
function RevisionsPanel({ projectId, tick, onRestored }: { projectId: string; tick: number; onRestored: (p: Project) => void }) {
  const revs = useAsync(() => api.revisions(projectId), [projectId, tick]);
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const restore = async (rid: string) => {
    setBusy(rid);
    setErr(null);
    try {
      onRestored(await api.restoreRevision(projectId, rid));
      revs.reload();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  };
  return (
    <Card>
      {err && <ErrorBanner>{err}</ErrorBanner>}
      {revs.loading && !revs.data ? (
        <Spinner />
      ) : !revs.data?.length ? (
        <p className="text-sm text-ink-400">No saved revisions yet.</p>
      ) : (
        <ol className="max-h-[60vh] space-y-1.5 overflow-y-auto pr-1">
          {revs.data.map((r, i) => (
            <li key={r.id} className="flex items-center gap-2 rounded-lg border border-white/[0.06] px-2.5 py-2">
              <div className="min-w-0 flex-1">
                <div className="truncate text-sm text-ink-100">
                  {r.note} {i === 0 && <Badge tone="green">current</Badge>}
                </div>
                <div className="text-xs text-ink-400">
                  {formatDate(r.created_at)} · {r.clip_count} clips · {formatDuration(r.duration)}
                </div>
              </div>
              {i > 0 && (
                <Button size="sm" variant="ghost" loading={busy === r.id} onClick={() => void restore(r.id)} icon={<RotateCcw className="size-3.5" />}>
                  Restore
                </Button>
              )}
            </li>
          ))}
        </ol>
      )}
    </Card>
  );
}

// ----------------------------------------------------------------------------- export settings
function ExportSettingsPanel({
  settings,
  formats,
  onChange,
}: {
  settings: ProjectSettings;
  formats?: Record<OutputFormat, boolean>;
  onChange: (s: ProjectSettings) => void;
}) {
  const set = (p: Partial<ProjectSettings>) => onChange({ ...settings, ...p });
  const unsupported = FORMATS.filter((f) => formats && !formats[f]);
  return (
    <Card>
      <div className="space-y-4">
        <Segmented label="Aspect ratio" value={settings.aspect} onChange={(v) => set({ aspect: v })} options={ASPECTS.map((a) => ({ value: a, label: a }))} />
        <Segmented
          label="Reframe (for vertical/square)"
          value={settings.reframe}
          onChange={(v) => set({ reframe: v })}
          options={[
            { value: "smart_crop", label: "Follow action" },
            { value: "blur_fill", label: "Blur fill" },
            { value: "center_crop", label: "Centre crop" },
          ]}
        />
        <Segmented label="Resolution" value={settings.resolution} onChange={(v) => set({ resolution: v })} options={RESOLUTIONS.map((r) => ({ value: r, label: r === "source" ? "Source" : r }))} />
        <Segmented
          label="Frame rate"
          value={settings.fps === null ? "source" : String(settings.fps)}
          onChange={(v) => set({ fps: v === "source" ? null : Number(v) })}
          options={[
            { value: "source", label: "Source" },
            { value: "30", label: "30" },
            { value: "60", label: "60" },
          ]}
        />
        <Segmented label="Quality" value={settings.quality} onChange={(v) => set({ quality: v })} options={QUALITIES.map((q) => ({ value: q, label: titleCase(q) }))} />
        <Segmented
          label="Format"
          value={settings.format}
          onChange={(v) => set({ format: v })}
          disabledOptions={unsupported}
          options={FORMATS.map((f) => ({ value: f, label: formatLabel(f), title: unsupported.includes(f) ? "Not supported by this server's FFmpeg" : undefined }))}
        />
        {unsupported.length > 0 && (
          <p className="text-xs text-amber-300">Unavailable on this server: {unsupported.map(formatLabel).join(", ")} (FFmpeg encoder missing).</p>
        )}
        <p className="text-xs text-ink-400">Settings are saved when you click Save, Render preview or Export.</p>
      </div>
    </Card>
  );
}
