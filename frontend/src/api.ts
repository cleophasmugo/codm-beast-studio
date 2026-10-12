/**
 * Typed client for the CODM Beast Studio FastAPI backend.
 * Types mirror backend/app/schemas.py. All calls use relative /api URLs.
 */
import { getToken } from "./lib/token";

// --------------------------------------------------------------------------- enums
export type Aspect = "16:9" | "9:16" | "1:1" | "4:5";
export type Resolution = "source" | "720p" | "1080p" | "1440p" | "2160p";
export type OutputFormat = "mp4_h264" | "mp4_h265" | "webm_vp9";
export type Quality = "draft" | "standard" | "high";
export type Transition = "cut" | "flash" | "fade" | "zoom" | "glitch" | "whip";
export type Reframe = "smart_crop" | "blur_fill" | "center_crop";
export type GameAudio = "keep" | "reduce" | "mute";
export type TextAnimation = "none" | "fade" | "pop" | "slide_left" | "slide_up" | "bounce";
export type PresetName =
  | "beast" | "cinematic" | "esports" | "smooth" | "neon" | "tiktok" | "youtube" | "shorts" | "showcase";
export type Look = "none" | "beast" | "cinematic" | "esports" | "clean" | "neon" | "warm" | "cold" | "vintage" | "bw";
export type Motion = "none" | "zoom_in" | "zoom_out" | "pan_left" | "pan_right";
export type MediaKind = "video" | "audio" | "image" | "sticker";
export type JobStatus = "queued" | "running" | "done" | "failed" | "cancelled";

export const TRANSITIONS: Transition[] = ["cut", "flash", "fade", "zoom", "glitch", "whip"];
export const MOTIONS: Motion[] = ["none", "zoom_in", "zoom_out", "pan_left", "pan_right"];
export const TEXT_ANIMATIONS: TextAnimation[] = ["none", "fade", "pop", "slide_left", "slide_up", "bounce"];
export const LOOKS: Look[] = ["none", "beast", "cinematic", "esports", "clean", "neon", "warm", "cold", "vintage", "bw"];
export const ASPECTS: Aspect[] = ["16:9", "9:16", "1:1", "4:5"];
export const RESOLUTIONS: Resolution[] = ["source", "720p", "1080p", "1440p", "2160p"];
export const QUALITIES: Quality[] = ["draft", "standard", "high"];
export const FORMATS: OutputFormat[] = ["mp4_h264", "mp4_h265", "webm_vp9"];

// --------------------------------------------------------------------------- settings
export interface EffectToggles {
  auto_enhance: boolean;
  sharpen: boolean;
  denoise: boolean;
  vignette: boolean;
  glow: boolean;
  motion_blur: boolean;
  speed_ramps: boolean;
  punch_in: boolean;
  shake: boolean;
  flash: boolean;
  light_leaks: boolean;
  chromatic: boolean;
  letterbox: boolean;
}

export interface ColorAdjust {
  brightness: number | null;
  contrast: number | null;
  saturation: number | null;
  gamma: number | null;
  shadows: number;
  highlights: number;
  sharpen_amount: number | null;
}

export interface HighlightWeights {
  motion: number;
  audio: number;
  transients: number;
  scene: number;
  flash: number;
  clarity: number;
  variety: number;
}

export interface ProjectSettings {
  preset: PresetName;
  target_duration: number | null;
  aspect: Aspect;
  reframe: Reframe;
  resolution: Resolution;
  fps: number | null;
  quality: Quality;
  format: OutputFormat;
  look: Look;
  look_strength: number;
  color: ColorAdjust;
  effects: EffectToggles;
  weights: HighlightWeights;
  beats_per_clip: number;
  transition: Transition | "auto";
  finale_last: boolean;
  music_id: string | null;
  music_volume: number;
  game_audio: GameAudio;
  ducking: boolean;
  duck_amount: number;
  normalize_audio: boolean;
  transition_sfx: boolean;
  image_duration: number;
  title: string;
  subtitle: string;
  outro_text: string;
  watermark_text: string;
  watermark_media_id: string | null;
  watermark_position: "top_left" | "top_right" | "bottom_left" | "bottom_right";
  watermark_opacity: number;
  clip_counter: boolean;
}

// --------------------------------------------------------------------------- timeline
export interface Keyframe {
  t: number;
  x: number;
  y: number;
  opacity: number;
}

export interface Overlay {
  id: string;
  type: "text" | "sticker" | "counter";
  text: string;
  media_id: string | null;
  start: number;
  end: number;
  x: number;
  y: number;
  scale: number;
  rotation: number;
  opacity: number;
  color: string;
  outline: string;
  animation: TextAnimation;
  keyframes: Keyframe[];
  layer: number;
}

export interface SpeedRamp {
  at: number;
  duration: number;
  speed: number;
}

export interface Clip {
  id: string;
  kind: "video" | "image" | "card";
  media_id: string | null;
  start: number;
  end: number;
  duration: number;
  ramp: SpeedRamp | null;
  transition: Transition;
  punch_in: boolean;
  shake: boolean;
  motion: Motion;
  crop_x: number | null;
  text: string;
  subtitle: string;
  score: number;
  reasons: string[];
  muted: boolean;
}

export interface MusicTrack {
  media_id: string;
  offset: number;
  volume: number;
  fade_in: number;
  fade_out: number;
}

export interface Timeline {
  version: number;
  clips: Clip[];
  overlays: Overlay[];
  music: MusicTrack | null;
  bpm: number | null;
  notes: string[];
}

/** Mirrors Clip.output_duration() in the backend. */
export function clipOutputDuration(c: Clip): number {
  if (c.kind !== "video") return c.duration;
  const src = Math.max(0, c.end - c.start);
  if (c.ramp) {
    const d = Math.min(c.ramp.duration, Math.max(0, src - c.ramp.at));
    return src - d + d / c.ramp.speed;
  }
  return src;
}

export function timelineDuration(t: Timeline): number {
  return t.clips.reduce((s, c) => s + clipOutputDuration(c), 0);
}

// --------------------------------------------------------------------------- API models
export interface MediaInfo {
  duration?: number;
  width?: number;
  height?: number;
  fps?: number;
  video_codec?: string;
  audio_codec?: string;
  has_audio?: boolean;
  has_video?: boolean;
  sample_rate?: number;
  channels?: number;
  bitrate?: number;
  container?: string;
  has_alpha?: boolean;
  animated?: boolean;
  megapixels?: number;
  [key: string]: unknown;
}

export interface Media {
  id: string;
  kind: MediaKind;
  name: string;
  folder: string;
  original_filename: string;
  mime: string;
  size_bytes: number;
  source: string;
  license: string;
  info: MediaInfo;
  has_analysis: boolean;
  created_at: string;
  url: string;
  thumb_url: string | null;
  contact_sheet_url: string | null;
}

export interface ExportItem {
  id: string;
  project_id: string | null;
  kind: "video" | "preview" | "image" | string;
  name: string;
  format: string;
  width: number;
  height: number;
  duration: number;
  size_bytes: number;
  settings: Record<string, unknown>;
  created_at: string;
  url: string;
  download_url: string;
  thumb_url: string | null;
}

export interface HighlightCandidate {
  media_id: string;
  start: number;
  end: number;
  peak: number;
  score: number;
  excitement?: number;
  clarity?: number;
  reasons: string[];
  signals?: Record<string, number>;
  evidence: string;
  events?: unknown[];
  crop_x?: number | null;
}

export interface MediaHighlights {
  name: string;
  duration: number;
  candidates: HighlightCandidate[];
  grid?: number;
  curve?: number[];
  scene_cuts?: number[];
  quiet_sections?: [number, number][];
  silences?: [number, number][];
  transient_count?: number;
  auto_color?: Record<string, unknown>;
}

export interface Highlights {
  media: Record<string, MediaHighlights>;
  selected: HighlightCandidate[];
  evidence_note: string;
}

export interface Project {
  id: string;
  name: string;
  media_ids: string[];
  settings: ProjectSettings;
  timeline: Timeline | null;
  highlights: Highlights | null;
  created_at: string;
  updated_at: string;
  revision_count: number;
  latest_export: ExportItem | null;
}

export interface Revision {
  id: string;
  note: string;
  created_at: string;
  clip_count: number;
  duration: number;
}

export interface JobResult {
  clip_count?: number;
  duration?: number;
  notes?: string[];
  export_id?: string;
  width?: number;
  height?: number;
  format?: string;
  size_bytes?: number;
  [key: string]: unknown;
}

export interface Job {
  id: string;
  project_id: string | null;
  kind: string;
  status: JobStatus;
  stage: string;
  progress: number;
  message: string;
  eta_seconds: number | null;
  result: JobResult | null;
  error: string | null;
  attempts: number;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
}

export interface Preset {
  id: PresetName;
  label: string;
  description: string;
  aspect: Aspect;
  target_duration: number | null;
}

export interface SystemInfo {
  version: string;
  ffmpeg: string;
  formats: Record<OutputFormat, boolean>;
  presets: Preset[];
  looks: Look[];
  job_backend: string;
  auth_required: boolean;
  limits: { max_upload_mb: number; max_video_minutes: number; max_audio_minutes: number; retention_days: number };
  storage: { total_bytes: number; by_area: Record<string, number>; work_bytes: number };
  detectors: string[];
}

export interface ProjectCreate {
  name: string;
  media_ids: string[];
  settings?: Partial<ProjectSettings> | null;
}

export interface ProjectUpdate {
  name?: string;
  media_ids?: string[];
  settings?: ProjectSettings;
}

export interface QuickMontageRequest {
  media_ids: string[];
  preset: PresetName;
  target_duration: number | null;
  music_id?: string | null;
  name?: string;
}

export interface CompareResult {
  before_url: string;
  after_url: string;
  filters: string[];
  auto_color: Record<string, unknown> & { reasons?: string[] };
}

// --------------------------------------------------------------------------- image studio
export interface ImageLayer {
  type: "text" | "sticker";
  text: string;
  media_id: string | null;
  x: number;
  y: number;
  scale: number;
  rotation: number;
  opacity: number;
  color: string;
  outline: string;
  shadow: boolean;
}

export type ImageAspect = "original" | "16:9" | "9:16" | "1:1" | "4:5" | "4:3";
export type ImageFrame = "none" | "thin" | "neon" | "polaroid";

export interface ImageEdit {
  crop: [number, number, number, number] | null;
  rotate: number;
  flip_h: boolean;
  aspect: ImageAspect;
  aspect_mode: "crop" | "blur_fill";
  max_size: number;
  auto_enhance: boolean;
  brightness: number;
  contrast: number;
  saturation: number;
  sharpness: number;
  gamma: number;
  warmth: number;
  look: Look;
  vignette: number;
  background_blur: number;
  frame: ImageFrame;
  frame_color: string;
  layers: ImageLayer[];
}

export const DEFAULT_IMAGE_EDIT: ImageEdit = {
  crop: null,
  rotate: 0,
  flip_h: false,
  aspect: "original",
  aspect_mode: "crop",
  max_size: 2160,
  auto_enhance: false,
  brightness: 1,
  contrast: 1,
  saturation: 1,
  sharpness: 1,
  gamma: 1,
  warmth: 0,
  look: "none",
  vignette: 0,
  background_blur: 0,
  frame: "none",
  frame_color: "#22D3EE",
  layers: [],
};

export interface ImageAnalysis {
  stats: Record<string, number | string | boolean>;
  suggested: Record<string, unknown> & { reasons?: string[] };
}

export interface ImageRenderResult {
  media: Media;
  export: ExportItem;
  auto: (Record<string, unknown> & { reasons?: string[] }) | null;
}

export interface AddToMontageRequest {
  project_id: string;
  media_id: string;
  duration: number;
  transition: Transition;
  motion: Motion;
  position?: number | null;
  snap_to_beats?: boolean;
}

// --------------------------------------------------------------------------- transport
export class ApiError extends Error {
  readonly status: number;
  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

interface ValidationItem {
  loc?: (string | number)[];
  msg?: string;
}

/** Turn FastAPI's `detail` (string or validation list) into one readable sentence. */
export function detailMessage(body: unknown, status: number): string {
  if (body && typeof body === "object" && "detail" in body) {
    const d = (body as { detail: unknown }).detail;
    if (typeof d === "string") return d;
    if (Array.isArray(d)) {
      return (d as ValidationItem[])
        .map((i) => {
          const where = (i.loc ?? []).filter((p) => p !== "body").join(".");
          return where ? `${where}: ${i.msg ?? "invalid"}` : (i.msg ?? "invalid");
        })
        .join("; ");
    }
  }
  if (status === 401) return "Missing or invalid access token. Set it in Settings.";
  if (status === 413) return "File is too large for this server.";
  if (status >= 500) return "Server error. Check the server log for details.";
  return `Request failed (HTTP ${status})`;
}

export function authHeaders(): Record<string, string> {
  const t = getToken();
  return t ? { Authorization: `Bearer ${t}` } : {};
}

/** Media/video/img URLs cannot send headers, so the token rides in the query string. */
export function mediaUrl(url: string | null | undefined): string {
  if (!url) return "";
  const t = getToken();
  if (!t) return url;
  return `${url}${url.includes("?") ? "&" : "?"}access_token=${encodeURIComponent(t)}`;
}

export async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = { Accept: "application/json", ...authHeaders() };
  if (init.body !== undefined && typeof init.body === "string") headers["Content-Type"] = "application/json";
  let res: Response;
  try {
    res = await fetch(path, { ...init, headers: { ...headers, ...(init.headers as Record<string, string>) } });
  } catch {
    throw new ApiError(0, "Cannot reach the server. Is the backend running?");
  }
  if (!res.ok) {
    let body: unknown = null;
    try {
      body = await res.json();
    } catch {
      /* not JSON */
    }
    throw new ApiError(res.status, detailMessage(body, res.status));
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

const json = (body: unknown): RequestInit => ({ body: JSON.stringify(body) });

async function postBlob(path: string, body: unknown, signal?: AbortSignal): Promise<{ blob: Blob; headers: Headers }> {
  let res: Response;
  try {
    res = await fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify(body),
      signal,
    });
  } catch (e) {
    if (e instanceof DOMException && e.name === "AbortError") throw e;
    throw new ApiError(0, "Cannot reach the server. Is the backend running?");
  }
  if (!res.ok) {
    let b: unknown = null;
    try {
      b = await res.json();
    } catch {
      /* ignore */
    }
    throw new ApiError(res.status, detailMessage(b, res.status));
  }
  return { blob: await res.blob(), headers: res.headers };
}

// --------------------------------------------------------------------------- uploads
export interface UploadHandle {
  promise: Promise<Media[]>;
  abort: () => void;
}

/** Upload with progress (fetch has no upload progress, so this uses XMLHttpRequest). */
export function uploadFiles(files: File[], onProgress?: (fraction: number) => void, folder = ""): UploadHandle {
  const xhr = new XMLHttpRequest();
  const promise = new Promise<Media[]>((resolve, reject) => {
    const form = new FormData();
    for (const f of files) form.append("files", f, f.name);
    form.append("folder", folder);
    xhr.open("POST", "/api/media");
    const h = authHeaders();
    for (const [k, v] of Object.entries(h)) xhr.setRequestHeader(k, v);
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable && onProgress) onProgress(e.loaded / e.total);
    };
    xhr.onload = () => {
      let body: unknown = null;
      try {
        body = JSON.parse(xhr.responseText);
      } catch {
        /* ignore */
      }
      if (xhr.status >= 200 && xhr.status < 300) resolve(body as Media[]);
      else reject(new ApiError(xhr.status, detailMessage(body, xhr.status)));
    };
    xhr.onerror = () => reject(new ApiError(0, "Upload failed: network error"));
    xhr.onabort = () => reject(new ApiError(0, "Upload cancelled"));
    xhr.send(form);
  });
  return { promise, abort: () => xhr.abort() };
}

// --------------------------------------------------------------------------- endpoints
const qs = (params: Record<string, string | number | boolean | null | undefined>): string => {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== null && v !== "") p.set(k, String(v));
  const s = p.toString();
  return s ? `?${s}` : "";
};

export const api = {
  // media
  listMedia: (kind?: MediaKind, folder?: string) => request<Media[]>(`/api/media${qs({ kind, folder })}`),
  getMedia: (id: string) => request<Media>(`/api/media/${id}`),
  updateMedia: (id: string, body: { name?: string; folder?: string }) =>
    request<Media>(`/api/media/${id}`, { method: "PATCH", ...json(body) }),
  deleteMedia: (id: string) => request<void>(`/api/media/${id}`, { method: "DELETE" }),
  frameUrl: (id: string, t: number) => `/api/media/${id}/frame?t=${Math.max(0, t).toFixed(2)}`,

  // projects
  listProjects: () => request<Project[]>("/api/projects"),
  getProject: (id: string) => request<Project>(`/api/projects/${id}`),
  createProject: (body: ProjectCreate) => request<Project>("/api/projects", { method: "POST", ...json(body) }),
  updateProject: (id: string, body: ProjectUpdate) =>
    request<Project>(`/api/projects/${id}`, { method: "PATCH", ...json(body) }),
  deleteProject: (id: string) => request<void>(`/api/projects/${id}`, { method: "DELETE" }),
  applyPreset: (id: string, preset: PresetName) =>
    request<Project>(`/api/projects/${id}/apply-preset/${preset}`, { method: "POST" }),
  saveTimeline: (id: string, timeline: Timeline, note = "Manual edit") =>
    request<Project>(`/api/projects/${id}/timeline`, { method: "PUT", ...json({ timeline, note }) }),
  revisions: (id: string) => request<Revision[]>(`/api/projects/${id}/revisions`),
  restoreRevision: (id: string, rev: string) =>
    request<Project>(`/api/projects/${id}/revisions/${rev}/restore`, { method: "POST" }),
  highlights: (id: string) => request<Highlights>(`/api/projects/${id}/highlights`),
  autoEdit: (id: string, settings?: ProjectSettings, render = true) =>
    request<Job>(`/api/projects/${id}/auto-edit`, { method: "POST", ...json({ settings: settings ?? null, render }) }),
  render: (id: string, preview: boolean) =>
    request<Job>(`/api/projects/${id}/render`, { method: "POST", ...json({ preview }) }),
  compare: (id: string, media_id: string, t: number) =>
    request<CompareResult>(`/api/projects/${id}/compare`, { method: "POST", ...json({ media_id, t }) }),
  quickMontage: (body: QuickMontageRequest) =>
    request<Job>("/api/montage/quick", { method: "POST", ...json(body) }),

  // jobs
  listJobs: (project_id?: string, limit = 50) => request<Job[]>(`/api/jobs${qs({ project_id, limit })}`),
  getJob: (id: string) => request<Job>(`/api/jobs/${id}`),
  cancelJob: (id: string) => request<Job>(`/api/jobs/${id}/cancel`, { method: "POST" }),
  retryJob: (id: string) => request<Job>(`/api/jobs/${id}/retry`, { method: "POST" }),

  // exports
  listExports: (project_id?: string) => request<ExportItem[]>(`/api/exports${qs({ project_id })}`),
  getExport: (id: string) => request<ExportItem>(`/api/exports/${id}`),
  deleteExport: (id: string) => request<void>(`/api/exports/${id}`, { method: "DELETE" }),

  // image studio
  analyzeImage: (id: string) => request<ImageAnalysis>(`/api/images/${id}/analyze`, { method: "POST" }),
  previewImage: async (id: string, edit: ImageEdit, signal?: AbortSignal) => {
    const { blob, headers } = await postBlob(`/api/images/${id}/preview`, edit, signal);
    const raw = headers.get("X-Auto-Reasons") ?? "";
    return { blob, reasons: raw ? raw.split("; ").filter(Boolean) : [] };
  },
  renderImage: (id: string, body: { edit: ImageEdit; format: "png" | "jpeg"; quality?: number; name?: string }) =>
    request<ImageRenderResult>(`/api/images/${id}/render`, { method: "POST", ...json({ save: true, ...body }) }),
  addToMontage: (body: AddToMontageRequest) =>
    request<Project>("/api/images/add-to-montage", { method: "POST", ...json(body) }),

  // system
  system: () => request<SystemInfo>("/api/system"),
  presets: () => request<Preset[]>("/api/presets"),
  cleanup: () => request<Record<string, unknown>>("/api/system/cleanup", { method: "POST" }),
};

export function isActive(job: Job | null | undefined): boolean {
  return !!job && (job.status === "queued" || job.status === "running");
}
