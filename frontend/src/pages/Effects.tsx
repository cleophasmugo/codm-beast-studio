import { Camera, Palette, Sparkles, Wand2 } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { api, LOOKS, mediaUrl, type ColorAdjust, type CompareResult, type EffectToggles, type Look } from "../api";
import { BeforeAfter } from "../components/BeforeAfter";
import { ProjectSelect, useSelectedProjectId } from "../components/ProjectSelect";
import { SaveBar } from "../components/SaveBar";
import { useToast } from "../components/Toast";
import { Badge, Button, Card, CardTitle, ErrorBanner, Note, PageHeader, SelectField, Slider, Spinner, Toggle, cx } from "../components/ui";
import { formatDuration, titleCase } from "../lib/format";
import { useAsync } from "../lib/hooks";
import { useProjectSettings } from "../lib/useProjectSettings";

const EFFECTS: { key: keyof EffectToggles; label: string; description: string }[] = [
  { key: "auto_enhance", label: "Auto enhance", description: "Measure each clip and fix exposure, contrast and colour" },
  { key: "sharpen", label: "Sharpen", description: "Crisper HUD and enemy outlines" },
  { key: "denoise", label: "Denoise", description: "Clean up compression noise when needed" },
  { key: "vignette", label: "Vignette", description: "Darker edges to focus the eye" },
  { key: "glow", label: "Glow", description: "Soft bloom on bright areas" },
  { key: "motion_blur", label: "Motion blur", description: "Smoother fast camera moves" },
  { key: "speed_ramps", label: "Speed ramps", description: "Slow-motion on the peak of a highlight" },
  { key: "punch_in", label: "Punch-in zoom", description: "Quick zoom on beat hits" },
  { key: "shake", label: "Camera shake", description: "Impact shake on big moments" },
  { key: "flash", label: "Flash hits", description: "White flashes on cuts" },
  { key: "light_leaks", label: "Light leaks", description: "Warm film-style light sweeps" },
  { key: "chromatic", label: "RGB split", description: "Chromatic aberration glitch hits" },
  { key: "letterbox", label: "Letterbox", description: "Cinematic black bars" },
  { key: "impact", label: "Kill impact", description: "White pop and hard shake on every detected kill" },
  { key: "velocity", label: "Velocity ramps", description: "Fast-slow-fast speed on every clip, with blur trails" },
  { key: "iris_intro", label: "Scope intro", description: "Open the montage as a circle growing out of black" },
];

type ColorKey = "brightness" | "contrast" | "saturation" | "gamma" | "sharpen_amount";
const COLOR_FIELDS: { key: ColorKey; label: string; min: number; max: number; neutral: number }[] = [
  { key: "brightness", label: "Brightness", min: -0.3, max: 0.3, neutral: 0 },
  { key: "contrast", label: "Contrast", min: 0.5, max: 1.8, neutral: 1 },
  { key: "saturation", label: "Saturation", min: 0, max: 2, neutral: 1 },
  { key: "gamma", label: "Gamma", min: 0.6, max: 1.6, neutral: 1 },
  { key: "sharpen_amount", label: "Sharpen amount", min: 0, max: 1.2, neutral: 0.5 },
];

export function EffectsPage() {
  const toast = useToast();
  const projectId = useSelectedProjectId();
  const ps = useProjectSettings(projectId);
  const s = ps.settings;
  const setColor = (patch: Partial<ColorAdjust>) => ps.update((x) => ({ ...x, color: { ...x.color, ...patch } }));

  return (
    <div className="space-y-6">
      <PageHeader title="Effects and Filters" subtitle="Switch every effect on or off, choose a colour grade, and check the result on a real rendered frame." />
      <Card>
        <ProjectSelect />
      </Card>
      {projectId && ps.loading && !s && <Spinner />}
      {ps.error && <ErrorBanner onRetry={ps.reload}>{ps.error}</ErrorBanner>}
      {s && ps.project && (
        <div className="grid gap-6 xl:grid-cols-2">
          <div className="min-w-0 space-y-6">
            <Card>
              <CardTitle icon={<Sparkles className="size-4" />}>Effects</CardTitle>
              <div className="grid gap-x-6 sm:grid-cols-2">
                {EFFECTS.map((e) => (
                  <Toggle
                    key={e.key}
                    label={e.label}
                    description={e.description}
                    checked={s.effects[e.key]}
                    onChange={(v) => ps.update((x) => ({ ...x, effects: { ...x.effects, [e.key]: v } }))}
                  />
                ))}
              </div>
            </Card>
            <Card>
              <CardTitle icon={<Palette className="size-4" />}>Colour grade</CardTitle>
              <div className="grid gap-4 sm:grid-cols-2">
                <SelectField label="Look" value={s.look} onChange={(e) => ps.update((x) => ({ ...x, look: e.target.value as Look }))}>
                  {LOOKS.map((l) => (
                    <option key={l} value={l}>
                      {l === "bw" ? "Black and white" : titleCase(l)}
                    </option>
                  ))}
                </SelectField>
                <Slider label="Look strength" value={s.look_strength} min={0} max={1.5} format={(v) => `${Math.round(v * 100)}%`} onChange={(v) => ps.update((x) => ({ ...x, look_strength: v }))} />
              </div>
              <h3 className="mt-5 mb-2 text-xs font-bold tracking-wide text-ink-300 uppercase">Manual colour</h3>
              <p className="mb-3 text-xs text-ink-400">
                <Badge tone="green">Auto</Badge> means the value is measured per clip by Auto Enhance. Switch a control to manual to override it.
              </p>
              <div className="space-y-3">
                {COLOR_FIELDS.map((f) => {
                  const v = s.color[f.key];
                  const auto = v === null;
                  return (
                    <div key={f.key} className={cx("rounded-xl border p-3", auto ? "border-white/[0.06]" : "border-cyber/30 bg-cyber/[0.04]")}>
                      <Toggle
                        label={f.label}
                        description={auto ? "Auto" : "Manual"}
                        checked={!auto}
                        onChange={(on) => setColor({ [f.key]: on ? f.neutral : null } as Partial<ColorAdjust>)}
                      />
                      {auto ? (
                        <Badge tone="green">Auto</Badge>
                      ) : (
                        <Slider label={`${f.label} value`} value={v} min={f.min} max={f.max} onChange={(nv) => setColor({ [f.key]: nv } as Partial<ColorAdjust>)} />
                      )}
                    </div>
                  );
                })}
                <Slider label="Shadows" value={s.color.shadows} min={-0.2} max={0.2} onChange={(v) => setColor({ shadows: v })} />
                <Slider label="Highlights" value={s.color.highlights} min={-0.2} max={0.2} onChange={(v) => setColor({ highlights: v })} />
              </div>
            </Card>
          </div>
          <div className="min-w-0">
            <ComparePanel projectId={ps.project.id} mediaIds={ps.project.media_ids} dirty={ps.dirty} save={ps.save} />
          </div>
        </div>
      )}
      <SaveBar dirty={ps.dirty} saving={ps.saving} onSave={async () => (await ps.save()) && toast.success("Effects saved")} onDiscard={ps.reload} />
    </div>
  );
}

function ComparePanel({
  projectId,
  mediaIds,
  dirty,
  save,
}: {
  projectId: string;
  mediaIds: string[];
  dirty: boolean;
  save: () => Promise<unknown>;
}) {
  const videos = useAsync(() => api.listMedia("video"), []);
  const projectVideos = useMemo(() => (videos.data ?? []).filter((m) => mediaIds.includes(m.id)), [videos.data, mediaIds]);
  const [mediaId, setMediaId] = useState("");
  const [t, setT] = useState(5);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<CompareResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const vid = projectVideos.find((v) => v.id === mediaId) ?? projectVideos[0];
  const dur = vid?.info.duration ?? 0;

  useEffect(() => {
    setResult(null);
  }, [projectId]);

  const run = async () => {
    if (!vid) return;
    setBusy(true);
    setError(null);
    try {
      if (dirty) await save(); // the comparison uses the saved project settings
      setResult(await api.compare(projectId, vid.id, Math.min(t, Math.max(0, dur - 0.1))));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card className="xl:sticky xl:top-6">
      <CardTitle icon={<Camera className="size-4" />}>Before / after</CardTitle>
      <Note>
        This is a real frame rendered by FFmpeg with this project's grade and effects (unsaved changes are saved first). Motion effects like
        shake, flashes and speed ramps only show in the video render.
      </Note>
      {videos.loading && !videos.data ? (
        <Spinner />
      ) : !projectVideos.length ? (
        <p className="mt-4 text-sm text-ink-400">This project has no gameplay videos to compare.</p>
      ) : (
        <div className="mt-4 space-y-3">
          <SelectField label="Video" value={vid?.id ?? ""} onChange={(e) => setMediaId(e.target.value)}>
            {projectVideos.map((v) => (
              <option key={v.id} value={v.id}>
                {v.name}
              </option>
            ))}
          </SelectField>
          <Slider label="Frame time" value={Math.min(t, dur)} min={0} max={Math.max(0.1, dur)} step={0.1} format={formatDuration} onChange={setT} />
          <Button variant="primary" className="w-full" onClick={run} loading={busy} icon={<Wand2 className="size-4" />} data-testid="compare">
            Render comparison frame
          </Button>
          {error && <ErrorBanner>{error}</ErrorBanner>}
          {result && (
            <div className="space-y-3" data-testid="compare-result">
              <BeforeAfter before={mediaUrl(result.before_url)} after={mediaUrl(result.after_url)} beforeLabel="Original" afterLabel="Graded (FFmpeg)" alt="Gameplay frame" />
              {Array.isArray(result.auto_color.reasons) && result.auto_color.reasons.length > 0 && (
                <div>
                  <p className="label">Auto colour decisions</p>
                  <ul className="space-y-0.5 text-xs text-ink-300">
                    {result.auto_color.reasons.map((r) => (
                      <li key={r}>• {r}</li>
                    ))}
                  </ul>
                </div>
              )}
              <details className="text-xs text-ink-400">
                <summary className="cursor-pointer text-ink-300">FFmpeg filter chain ({result.filters.length})</summary>
                <code className="mt-1 block rounded-lg bg-ink-950 p-2 font-mono break-all text-cyan-200">{result.filters.join(",") || "(none)"}</code>
              </details>
            </div>
          )}
        </div>
      )}
    </Card>
  );
}
