import { AnimatePresence, motion } from "framer-motion";
import {
  ArrowDown,
  ArrowUp,
  Crop,
  Download,
  Film,
  FlipHorizontal,
  ImageIcon,
  Layers,
  Loader2,
  Palette,
  Plus,
  RotateCcw,
  Sparkles,
  Sticker,
  Trash2,
  Type,
  Wand2,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import {
  api,
  DEFAULT_IMAGE_EDIT,
  LOOKS,
  MOTIONS,
  TRANSITIONS,
  mediaUrl,
  type ImageAspect,
  type ImageEdit,
  type ImageFrame,
  type ImageLayer,
  type ImageRenderResult,
  type Job,
  type Look,
  type Media,
  type Motion,
  type Project,
  type Transition,
} from "../api";
import { BeforeAfter } from "../components/BeforeAfter";
import { DownloadLink } from "../components/ExportPlayer";
import { JobProgressCard } from "../components/JobProgressCard";
import { JobResult } from "../components/JobResult";
import { MediaThumb } from "../components/MediaThumb";
import { useToast } from "../components/Toast";
import { UploadZone } from "../components/UploadZone";
import {
  Badge,
  Button,
  Card,
  CardTitle,
  Empty,
  ErrorBanner,
  IconButton,
  Note,
  PageHeader,
  Segmented,
  SelectField,
  Slider,
  Spinner,
  TextField,
  Toggle,
  cx,
} from "../components/ui";
import { clamp, formatBytes, titleCase } from "../lib/format";
import { useAsync, useDebounced } from "../lib/hooks";
import { moveItem } from "../lib/timelineHistory";
import { setQueryParam, useLocation } from "../lib/router";

type Tab = "adjust" | "transform" | "layers" | "export";
type View = "edited" | "original" | "split";

const ASPECT_OPTIONS: ImageAspect[] = ["original", "16:9", "9:16", "1:1", "4:5", "4:3"];
const FRAMES: ImageFrame[] = ["none", "thin", "neon", "polaroid"];

/** One-tap looks for screenshots: a bundle of slider values. */
const LOOK_PRESETS: { id: string; label: string; patch: Partial<ImageEdit> }[] = [
  { id: "natural", label: "Natural", patch: { look: "none", contrast: 1.05, saturation: 1.05, sharpness: 1.2 } },
  { id: "punchy", label: "Punchy", patch: { look: "beast", contrast: 1.2, saturation: 1.25, sharpness: 1.5, vignette: 0.3 } },
  { id: "neon", label: "Neon", patch: { look: "neon", saturation: 1.3, warmth: -0.2, vignette: 0.35, frame: "neon", frame_color: "#A855F7" } },
  { id: "cinema", label: "Cinematic", patch: { look: "cinematic", contrast: 1.1, warmth: 0.25, vignette: 0.45 } },
  { id: "clean", label: "Esports Clean", patch: { look: "esports", contrast: 1.08, sharpness: 1.6, saturation: 1.1 } },
  { id: "mono", label: "Mono", patch: { look: "bw", contrast: 1.25, vignette: 0.3 } },
];

function newLayer(type: "text" | "sticker", media_id: string | null = null): ImageLayer {
  return {
    type,
    text: type === "text" ? "BEAST MODE" : "",
    media_id,
    x: 0.5,
    y: type === "text" ? 0.15 : 0.5,
    scale: 1,
    rotation: 0,
    opacity: 1,
    color: "#FFFFFF",
    outline: "#000000",
    shadow: true,
  };
}

function geometryUnchanged(e: ImageEdit): boolean {
  return !e.crop && e.rotate === 0 && e.aspect === "original" && e.frame === "none";
}

export function ImageStudio() {
  const toast = useToast();
  const { query } = useLocation();
  const images = useAsync(() => api.listMedia("image"), []);
  const stickers = useAsync(() => api.listMedia("sticker"), []);

  const selectedId = query.get("image");
  const current = images.data?.find((m) => m.id === selectedId) ?? images.data?.[0] ?? null;

  const [edit, setEdit] = useState<ImageEdit>(DEFAULT_IMAGE_EDIT);
  const [tab, setTab] = useState<Tab>("adjust");
  const [view, setView] = useState<View>("edited");
  const [activeLayer, setActiveLayer] = useState<number | null>(null);

  const [preview, setPreview] = useState<string | null>(null);
  const [previewing, setPreviewing] = useState(false);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [reasons, setReasons] = useState<string[]>([]);
  const [analysis, setAnalysis] = useState<string[] | null>(null);
  const [analyzing, setAnalyzing] = useState(false);

  // reset edit state when switching images
  useEffect(() => {
    setEdit(DEFAULT_IMAGE_EDIT);
    setActiveLayer(null);
    setReasons([]);
    setAnalysis(null);
    setView("edited");
  }, [current?.id]);

  const patch = useCallback((p: Partial<ImageEdit>) => setEdit((e) => ({ ...e, ...p })), []);
  const patchLayer = (i: number, p: Partial<ImageLayer>) =>
    setEdit((e) => ({ ...e, layers: e.layers.map((l, j) => (j === i ? { ...l, ...p } : l)) }));

  // live preview (debounced, previous request aborted)
  const debounced = useDebounced(edit, 350);
  const urlRef = useRef<string | null>(null);
  useEffect(() => {
    if (!current) return;
    const ctl = new AbortController();
    setPreviewing(true);
    api
      .previewImage(current.id, { ...debounced, max_size: 1280 }, ctl.signal)
      .then(({ blob, reasons: r }) => {
        const url = URL.createObjectURL(blob);
        if (urlRef.current) URL.revokeObjectURL(urlRef.current);
        urlRef.current = url;
        setPreview(url);
        setReasons(r);
        setPreviewError(null);
        setPreviewing(false);
      })
      .catch((e: unknown) => {
        if (e instanceof DOMException && e.name === "AbortError") return;
        setPreviewError(e instanceof Error ? e.message : String(e));
        setPreviewing(false);
      });
    return () => ctl.abort();
  }, [current, debounced]);
  useEffect(() => () => {
    if (urlRef.current) URL.revokeObjectURL(urlRef.current);
  }, []);

  const autoEnhance = async () => {
    if (!current) return;
    const turnOn = !edit.auto_enhance;
    patch({ auto_enhance: turnOn });
    if (!turnOn) {
      setAnalysis(null);
      return;
    }
    setAnalyzing(true);
    try {
      const a = await api.analyzeImage(current.id);
      setAnalysis(a.suggested.reasons ?? []);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : String(e));
    } finally {
      setAnalyzing(false);
    }
  };

  const onUploaded = useCallback(
    (items: Media[]) => {
      const imgs = items.filter((m) => m.kind === "image");
      images.setData((prev) => [...imgs, ...(prev ?? [])]);
      if (imgs[0]) setQueryParam("image", imgs[0].id);
      const st = items.filter((m) => m.kind === "sticker");
      if (st.length) stickers.setData((prev) => [...st, ...(prev ?? [])]);
    },
    [images, stickers],
  );

  const placeLayer = (e: React.MouseEvent<HTMLImageElement>) => {
    if (activeLayer === null) return;
    const r = e.currentTarget.getBoundingClientRect();
    patchLayer(activeLayer, {
      x: Number(clamp((e.clientX - r.left) / r.width, 0, 1).toFixed(3)),
      y: Number(clamp((e.clientY - r.top) / r.height, 0, 1).toFixed(3)),
    });
  };

  const canSplit = geometryUnchanged(edit);
  const shownReasons = reasons.length ? reasons : (analysis ?? []);

  if (images.loading && !images.data) return <Spinner label="Loading images" />;

  return (
    <div className="space-y-6">
      <PageHeader
        title="Image Studio"
        subtitle="Enhance screenshots, add text and stickers, export them or drop them into a montage as moving scenes."
      />
      {images.error && <ErrorBanner onRetry={images.reload}>{images.error}</ErrorBanner>}

      <Card>
        <CardTitle icon={<ImageIcon className="size-4" />}>Choose a screenshot</CardTitle>
        {images.data?.length ? (
          <ul className="flex gap-3 overflow-x-auto pb-2" aria-label="Screenshots">
            {images.data.map((m) => (
              <li key={m.id} className="w-36 shrink-0">
                <button
                  type="button"
                  aria-pressed={current?.id === m.id}
                  onClick={() => setQueryParam("image", m.id)}
                  className={cx(
                    "block w-full rounded-xl border p-1 text-left transition",
                    current?.id === m.id ? "border-cyber/70 bg-cyber/10" : "border-white/[0.08] hover:border-white/25",
                  )}
                >
                  <MediaThumb media={m} />
                  <span className="mt-1 block truncate px-0.5 text-[11px] font-semibold text-ink-200">{m.name}</span>
                </button>
              </li>
            ))}
          </ul>
        ) : (
          <Empty title="No screenshots yet">Upload one below.</Empty>
        )}
        <div className="mt-3">
          <UploadZone compact accept=".jpg,.jpeg,.png,.webp,.bmp,.gif,image/*" title="Upload screenshots or stickers" hint="JPG, PNG, WebP. PNGs with transparency become stickers." onUploaded={onUploaded} />
        </div>
      </Card>

      {current && (
        <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_380px]">
          {/* preview */}
          <Card className="min-w-0 lg:sticky lg:top-6 lg:self-start">
            <div className="mb-3 flex flex-wrap items-center gap-2">
              <Segmented
                label="View"
                value={view}
                onChange={setView}
                disabledOptions={canSplit ? [] : ["split"]}
                options={[
                  { value: "edited", label: "Edited" },
                  { value: "original", label: "Original" },
                  { value: "split", label: "Before / after", title: canSplit ? "Drag to compare" : "Available when crop, rotate, aspect and frame are unchanged" },
                ]}
              />
              <span className="ml-auto flex items-center gap-2 text-xs text-ink-400">
                {previewing && <Loader2 className="size-3.5 animate-spin text-cyber" aria-hidden />}
                {previewing ? "Rendering preview…" : "Live preview"}
              </span>
            </div>
            <div className="checker relative grid min-h-48 place-items-center overflow-hidden rounded-xl border border-white/10" data-testid="image-preview">
              {view === "split" && canSplit && preview ? (
                <div className="w-full">
                  <BeforeAfter before={mediaUrl(current.url)} after={preview} alt={current.name} />
                </div>
              ) : view === "original" ? (
                <img src={mediaUrl(current.url)} alt={`${current.name} (original)`} className="max-h-[65vh] w-auto" />
              ) : preview ? (
                <img
                  src={preview}
                  alt={`${current.name} (edited preview)`}
                  onClick={placeLayer}
                  className={cx("max-h-[65vh] w-auto", activeLayer !== null && "cursor-crosshair")}
                />
              ) : (
                <Spinner label="Rendering preview" />
              )}
            </div>
            {activeLayer !== null && view === "edited" && (
              <p className="mt-2 text-xs text-ink-400">Tip: click the preview to move the selected layer there.</p>
            )}
            {previewError && (
              <div className="mt-3">
                <ErrorBanner>{previewError}</ErrorBanner>
              </div>
            )}
            <AnimatePresence>
              {edit.auto_enhance && (
                <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} exit={{ opacity: 0, height: 0 }} className="mt-3">
                  <div className="rounded-xl border border-toxic/30 bg-toxic/[0.06] p-3" data-testid="auto-reasons">
                    <p className="mb-1 flex items-center gap-1.5 text-xs font-bold text-lime-200 uppercase">
                      <Sparkles className="size-3.5" aria-hidden /> Auto Enhance applied
                    </p>
                    {analyzing && !shownReasons.length ? (
                      <p className="text-xs text-ink-300">Measuring exposure, contrast and colour…</p>
                    ) : shownReasons.length ? (
                      <ul className="space-y-0.5 text-xs text-ink-200">
                        {shownReasons.map((r) => (
                          <li key={r}>• {r}</li>
                        ))}
                      </ul>
                    ) : (
                      <p className="text-xs text-ink-300">This image already looks well exposed; only light sharpening was needed.</p>
                    )}
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          </Card>

          {/* controls */}
          <div className="min-w-0 space-y-4">
            <div role="tablist" aria-label="Image tools" className="grid grid-cols-4 gap-1 rounded-xl border border-white/[0.08] bg-ink-900/70 p-1">
              {(
                [
                  ["adjust", "Adjust", <Palette key="a" className="size-4" />],
                  ["transform", "Crop", <Crop key="c" className="size-4" />],
                  ["layers", "Layers", <Layers key="l" className="size-4" />],
                  ["export", "Export", <Download key="e" className="size-4" />],
                ] as [Tab, string, ReactNode][]
              ).map(([id, label, icon]) => (
                <button
                  key={id}
                  role="tab"
                  type="button"
                  aria-selected={tab === id}
                  onClick={() => setTab(id)}
                  className={cx(
                    "flex flex-col items-center gap-0.5 rounded-lg py-2 text-[11px] font-semibold transition sm:flex-row sm:justify-center sm:gap-1.5 sm:text-xs",
                    tab === id ? "bg-gradient-to-r from-cyber/25 to-volt/20 text-white" : "text-ink-300 hover:text-white",
                  )}
                >
                  {icon}
                  {label}
                </button>
              ))}
            </div>

            {tab === "adjust" && (
              <Card>
                <Button
                  variant={edit.auto_enhance ? "success" : "primary"}
                  className="w-full"
                  onClick={autoEnhance}
                  loading={analyzing}
                  icon={<Wand2 className="size-4" />}
                  data-testid="auto-enhance"
                >
                  {edit.auto_enhance ? "Auto Enhance on (tap to turn off)" : "Auto Enhance Image"}
                </Button>
                <div className="mt-4">
                  <p className="label">Looks</p>
                  <div className="grid grid-cols-3 gap-1.5">
                    {LOOK_PRESETS.map((l) => (
                      <Button key={l.id} size="sm" variant="secondary" onClick={() => patch(l.patch)}>
                        {l.label}
                      </Button>
                    ))}
                  </div>
                </div>
                <div className="mt-4 space-y-1">
                  <Slider label="Brightness" value={edit.brightness} min={0.3} max={2} onChange={(v) => patch({ brightness: v })} />
                  <Slider label="Contrast" value={edit.contrast} min={0.3} max={2} onChange={(v) => patch({ contrast: v })} />
                  <Slider label="Saturation" value={edit.saturation} min={0} max={2.5} onChange={(v) => patch({ saturation: v })} />
                  <Slider label="Sharpness" value={edit.sharpness} min={0} max={3} onChange={(v) => patch({ sharpness: v })} />
                  <Slider label="Gamma" value={edit.gamma} min={0.5} max={2} onChange={(v) => patch({ gamma: v })} />
                  <Slider label="Warmth" value={edit.warmth} min={-1} max={1} onChange={(v) => patch({ warmth: v })} />
                  <SelectField label="Colour grade" value={edit.look} onChange={(e) => patch({ look: e.target.value as Look })} className="pt-2">
                    {LOOKS.map((l) => (
                      <option key={l} value={l}>
                        {l === "bw" ? "Black and white" : titleCase(l)}
                      </option>
                    ))}
                  </SelectField>
                  <Slider label="Vignette" value={edit.vignette} min={0} max={1} onChange={(v) => patch({ vignette: v })} />
                  <Slider label="Background blur" value={edit.background_blur} min={0} max={1} onChange={(v) => patch({ background_blur: v })} />
                </div>
                <Button className="mt-3" size="sm" variant="ghost" icon={<RotateCcw className="size-3.5" />} onClick={() => setEdit((e) => ({ ...DEFAULT_IMAGE_EDIT, layers: e.layers }))}>
                  Reset adjustments
                </Button>
              </Card>
            )}

            {tab === "transform" && (
              <Card>
                <div className="space-y-4">
                  <Segmented label="Aspect" value={edit.aspect} onChange={(v) => patch({ aspect: v })} options={ASPECT_OPTIONS.map((a) => ({ value: a, label: a === "original" ? "Original" : a }))} />
                  <Segmented
                    label="Fit mode"
                    value={edit.aspect_mode}
                    onChange={(v) => patch({ aspect_mode: v })}
                    options={[
                      { value: "crop", label: "Crop to fill" },
                      { value: "blur_fill", label: "Blur fill (keep everything)" },
                    ]}
                  />
                  <Slider label="Rotate" value={edit.rotate} min={-180} max={180} step={1} format={(v) => `${v.toFixed(0)}°`} onChange={(v) => patch({ rotate: v })} />
                  <Toggle label="Flip horizontally" checked={edit.flip_h} onChange={(v) => patch({ flip_h: v })} />
                  <div className="rounded-xl border border-white/[0.08] p-3">
                    <Toggle
                      label="Manual crop"
                      description="Relative to the original image (0 to 1)"
                      checked={!!edit.crop}
                      onChange={(v) => patch({ crop: v ? [0.1, 0.1, 0.8, 0.8] : null })}
                    />
                    {edit.crop && (
                      <div className="mt-2">
                        {(["X", "Y", "Width", "Height"] as const).map((lab, i) => (
                          <Slider
                            key={lab}
                            label={lab}
                            value={edit.crop![i]}
                            min={i < 2 ? 0 : 0.05}
                            max={i < 2 ? 0.95 : 1}
                            onChange={(v) => {
                              const c = [...edit.crop!] as [number, number, number, number];
                              c[i] = v;
                              // keep the crop inside the image
                              if (i === 0 || i === 2) c[2] = Math.min(c[2], 1 - c[0]);
                              if (i === 1 || i === 3) c[3] = Math.min(c[3], 1 - c[1]);
                              patch({ crop: c });
                            }}
                          />
                        ))}
                      </div>
                    )}
                  </div>
                  <Segmented label="Frame" value={edit.frame} onChange={(v) => patch({ frame: v })} options={FRAMES.map((f) => ({ value: f, label: titleCase(f) }))} />
                  {edit.frame !== "none" && (
                    <ColorInput label="Frame colour" value={edit.frame_color} onChange={(v) => patch({ frame_color: v })} />
                  )}
                  <Button size="sm" variant="ghost" icon={<FlipHorizontal className="size-3.5" />} onClick={() => patch({ crop: null, rotate: 0, flip_h: false, aspect: "original", aspect_mode: "crop", frame: "none" })}>
                    Reset crop and frame
                  </Button>
                </div>
              </Card>
            )}

            {tab === "layers" && (
              <LayersPanel
                edit={edit}
                setEdit={setEdit}
                stickers={stickers.data ?? []}
                active={activeLayer}
                setActive={setActiveLayer}
                patchLayer={patchLayer}
              />
            )}

            {tab === "export" && <ExportPanel media={current} edit={edit} />}
          </div>
        </div>
      )}
    </div>
  );
}

function ColorInput({ label, value, onChange }: { label: string; value: string; onChange: (v: string) => void }) {
  return (
    <label className="flex items-center justify-between gap-3 text-xs font-medium text-ink-200">
      {label}
      <span className="flex items-center gap-2">
        <span className="font-mono text-ink-300">{value.toUpperCase()}</span>
        <input type="color" value={value} onChange={(e) => onChange(e.target.value.toUpperCase())} className="h-8 w-10 cursor-pointer rounded border border-white/10 bg-transparent" />
      </span>
    </label>
  );
}

function LayersPanel({
  edit,
  setEdit,
  stickers,
  active,
  setActive,
  patchLayer,
}: {
  edit: ImageEdit;
  setEdit: React.Dispatch<React.SetStateAction<ImageEdit>>;
  stickers: Media[];
  active: number | null;
  setActive: (i: number | null) => void;
  patchLayer: (i: number, p: Partial<ImageLayer>) => void;
}) {
  const [picking, setPicking] = useState(false);
  const add = (l: ImageLayer) => {
    setEdit((e) => ({ ...e, layers: [...e.layers, l] }));
    setActive(edit.layers.length);
    setPicking(false);
  };
  const move = (i: number, d: -1 | 1) => {
    setEdit((e) => ({ ...e, layers: moveItem(e.layers, i, i + d) }));
    setActive(i + d);
  };
  const remove = (i: number) => {
    setEdit((e) => ({ ...e, layers: e.layers.filter((_, j) => j !== i) }));
    setActive(null);
  };
  const stickerName = (id: string | null) => stickers.find((s) => s.id === id)?.name ?? "Sticker";
  const l = active !== null ? edit.layers[active] : undefined;

  return (
    <Card>
      <div className="flex gap-2">
        <Button size="sm" variant="secondary" icon={<Type className="size-3.5" />} onClick={() => add(newLayer("text"))}>
          Add text
        </Button>
        <Button size="sm" variant="secondary" icon={<Sticker className="size-3.5" />} onClick={() => setPicking((v) => !v)} aria-expanded={picking}>
          Add sticker
        </Button>
      </div>
      {picking && (
        <div className="mt-3 rounded-xl border border-white/[0.08] p-2">
          {stickers.length ? (
            <ul className="grid grid-cols-4 gap-2">
              {stickers.map((s) => (
                <li key={s.id}>
                  <button type="button" onClick={() => add(newLayer("sticker", s.id))} className="checker block w-full rounded-lg border border-white/10 p-1 hover:border-cyber/60" title={s.name} aria-label={`Add sticker ${s.name}`}>
                    <img src={mediaUrl(s.thumb_url ?? s.url)} alt="" className="aspect-square w-full object-contain" />
                  </button>
                </li>
              ))}
            </ul>
          ) : (
            <p className="p-2 text-xs text-ink-400">No stickers. Upload a transparent PNG.</p>
          )}
        </div>
      )}

      <ol className="mt-4 space-y-1.5" aria-label="Layers (bottom to top)">
        {edit.layers.length === 0 && <li className="text-sm text-ink-400">No layers yet.</li>}
        {edit.layers.map((layer, i) => (
          <li
            key={i}
            className={cx(
              "flex items-center gap-1 rounded-lg border px-2 py-1.5",
              active === i ? "border-cyber/60 bg-cyber/10" : "border-white/[0.08] bg-ink-900/60",
            )}
          >
            <button type="button" className="flex min-w-0 flex-1 items-center gap-2 text-left text-sm" onClick={() => setActive(active === i ? null : i)} aria-pressed={active === i}>
              {layer.type === "text" ? <Type className="size-4 shrink-0 text-cyber" aria-hidden /> : <Sticker className="size-4 shrink-0 text-volt" aria-hidden />}
              <span className="truncate text-ink-100">{layer.type === "text" ? layer.text || "(empty text)" : stickerName(layer.media_id)}</span>
            </button>
            <IconButton label="Move layer down" onClick={() => move(i, -1)} disabled={i === 0}>
              <ArrowDown className="size-4" />
            </IconButton>
            <IconButton label="Move layer up" onClick={() => move(i, 1)} disabled={i === edit.layers.length - 1}>
              <ArrowUp className="size-4" />
            </IconButton>
            <IconButton label="Delete layer" onClick={() => remove(i)} className="hover:text-rose-400">
              <Trash2 className="size-4" />
            </IconButton>
          </li>
        ))}
      </ol>

      {l && active !== null && (
        <div className="mt-4 space-y-1 border-t border-white/5 pt-4">
          {l.type === "text" && <TextField label="Text" value={l.text} maxLength={200} onChange={(v) => patchLayer(active, { text: v })} />}
          <Slider label="X position" value={l.x} min={0} max={1} onChange={(v) => patchLayer(active, { x: v })} />
          <Slider label="Y position" value={l.y} min={0} max={1} onChange={(v) => patchLayer(active, { y: v })} />
          <Slider label="Scale" value={l.scale} min={0.1} max={6} onChange={(v) => patchLayer(active, { scale: v })} />
          <Slider label="Rotation" value={l.rotation} min={-180} max={180} step={1} format={(v) => `${v.toFixed(0)}°`} onChange={(v) => patchLayer(active, { rotation: v })} />
          <Slider label="Opacity" value={l.opacity} min={0} max={1} format={(v) => `${Math.round(v * 100)}%`} onChange={(v) => patchLayer(active, { opacity: v })} />
          {l.type === "text" && (
            <div className="space-y-2 pt-2">
              <ColorInput label="Text colour" value={l.color} onChange={(v) => patchLayer(active, { color: v })} />
              <ColorInput label="Outline colour" value={l.outline} onChange={(v) => patchLayer(active, { outline: v })} />
            </div>
          )}
          <Toggle label="Drop shadow" checked={l.shadow} onChange={(v) => patchLayer(active, { shadow: v })} />
        </div>
      )}
    </Card>
  );
}

function ExportPanel({ media, edit }: { media: Media; edit: ImageEdit }) {
  const toast = useToast();
  const projects = useAsync(() => api.listProjects(), []);
  const [format, setFormat] = useState<"png" | "jpeg">("png");
  const [quality, setQuality] = useState(92);
  const [name, setName] = useState("");
  const [rendering, setRendering] = useState(false);
  const [result, setResult] = useState<ImageRenderResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setResult(null);
    setName(`${media.name} enhanced`);
  }, [media.id, media.name]);

  const render = async () => {
    setRendering(true);
    setError(null);
    try {
      const r = await api.renderImage(media.id, { edit, format, quality, name: name.trim() || undefined });
      setResult(r);
      toast.success("Image exported");
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setRendering(false);
    }
  };

  return (
    <div className="space-y-4">
      <Card>
        <CardTitle icon={<Download className="size-4" />}>Export image</CardTitle>
        <div className="space-y-3">
          <Segmented
            label="Format"
            value={format}
            onChange={setFormat}
            options={[
              { value: "png", label: "PNG (lossless)" },
              { value: "jpeg", label: "JPEG (smaller)" },
            ]}
          />
          {format === "jpeg" && <Slider label="JPEG quality" value={quality} min={40} max={100} step={1} format={(v) => String(v)} onChange={setQuality} />}
          <TextField label="File name" value={name} onChange={setName} maxLength={200} />
          <Button variant="primary" className="w-full" onClick={render} loading={rendering} icon={<Download className="size-4" />} data-testid="export-image">
            Export as {format.toUpperCase()}
          </Button>
          {error && <ErrorBanner>{error}</ErrorBanner>}
        </div>
        {result && (
          <motion.div initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} className="mt-4 space-y-2" data-testid="image-export-result">
            <img src={mediaUrl(result.export.url)} alt={result.export.name} className="checker w-full rounded-lg border border-white/10" />
            <div className="flex flex-wrap items-center gap-2">
              <span className="min-w-0 flex-1 truncate text-xs font-semibold text-white">{result.export.name}</span>
              <Badge>
                {result.export.width}×{result.export.height}
              </Badge>
              <Badge>{formatBytes(result.export.size_bytes)}</Badge>
            </div>
            <DownloadLink item={result.export} />
            <p className="text-xs text-ink-400">Saved to your library as a new screenshot, so you can use it in montages.</p>
          </motion.div>
        )}
      </Card>

      <AddToMontage
        mediaId={result?.media.id ?? media.id}
        mediaName={result?.media.name ?? media.name}
        usingExport={!!result}
        projects={projects.data ?? []}
        loading={projects.loading && !projects.data}
        error={projects.error}
      />
    </div>
  );
}

function AddToMontage({
  mediaId,
  mediaName,
  usingExport,
  projects,
  loading,
  error,
}: {
  mediaId: string;
  mediaName: string;
  usingExport: boolean;
  projects: Project[];
  loading: boolean;
  error: string | null;
}) {
  const toast = useToast();
  const [projectId, setProjectId] = useState("");
  const [duration, setDuration] = useState(2.5);
  const [transition, setTransition] = useState<Transition>("flash");
  const [motionKind, setMotion] = useState<Motion>("zoom_in");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [added, setAdded] = useState<Project | null>(null);
  const [renderJob, setRenderJob] = useState<string | null>(null);
  const [rendered, setRendered] = useState<Job | null>(null);

  const pid = projectId || projects[0]?.id || "";
  const project = useMemo(() => projects.find((p) => p.id === pid), [projects, pid]);

  const add = async () => {
    setBusy(true);
    setErr(null);
    setRendered(null);
    setRenderJob(null);
    try {
      const p = await api.addToMontage({ project_id: pid, media_id: mediaId, duration, transition, motion: motionKind });
      setAdded(p);
      toast.success(`Added to ${p.name}`);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const rerender = async () => {
    if (!added) return;
    setErr(null);
    try {
      const j = added.timeline ? await api.render(added.id, false) : await api.autoEdit(added.id, undefined, true);
      setRenderJob(j.id);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    }
  };

  return (
    <Card>
      <CardTitle icon={<Film className="size-4" />}>Add to Montage</CardTitle>
      {loading ? (
        <Spinner />
      ) : error ? (
        <ErrorBanner>{error}</ErrorBanner>
      ) : !projects.length ? (
        <p className="text-sm text-ink-400">Create a montage first (Dashboard or Auto Edit), then add screenshots to it.</p>
      ) : (
        <div className="space-y-3">
          <Note>
            Adds <strong className="text-white">{mediaName}</strong> {usingExport ? "(your exported edit)" : "(original, export first to use your edits)"} as a
            timed scene with motion.
          </Note>
          <SelectField label="Project" value={pid} onChange={(e) => setProjectId(e.target.value)} data-testid="atm-project">
            {projects.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </SelectField>
          <Slider label="Scene length" value={duration} min={0.5} max={10} step={0.5} format={(v) => `${v.toFixed(1)}s`} onChange={setDuration} />
          <div className="grid grid-cols-2 gap-3">
            <SelectField label="Transition" value={transition} onChange={(e) => setTransition(e.target.value as Transition)}>
              {TRANSITIONS.map((t) => (
                <option key={t} value={t}>
                  {titleCase(t)}
                </option>
              ))}
            </SelectField>
            <SelectField label="Motion" value={motionKind} onChange={(e) => setMotion(e.target.value as Motion)}>
              {MOTIONS.map((m) => (
                <option key={m} value={m}>
                  {titleCase(m)}
                </option>
              ))}
            </SelectField>
          </div>
          <Button variant="secondary" className="w-full" onClick={add} loading={busy} disabled={!pid} icon={<Plus className="size-4" />} data-testid="add-to-montage">
            Add to {project?.name ?? "project"}
          </Button>
          {err && <ErrorBanner>{err}</ErrorBanner>}
          {added && (
            <div className="space-y-3 rounded-xl border border-toxic/30 bg-toxic/[0.05] p-3" data-testid="atm-done">
              <p className="text-sm text-lime-100">
                {added.timeline
                  ? `Added as a scene. The timeline now has ${added.timeline.clips.length} clips.`
                  : "Added to the project. It will be used by the next Auto Edit."}
              </p>
              <Button variant="primary" size="sm" onClick={rerender} disabled={!!renderJob && !rendered} data-testid="rerender">
                {added.timeline ? "Re-render montage" : "Run Auto Edit"}
              </Button>
              {renderJob && (
                <JobProgressCard key={renderJob} jobId={renderJob} title="Re-rendering" onFinish={(j) => j.status === "done" && setRendered(j)} />
              )}
              {rendered && <JobResult job={rendered} />}
            </div>
          )}
        </div>
      )}
    </Card>
  );
}
