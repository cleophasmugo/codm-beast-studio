/** Small display helpers. Pure functions, unit tested. */

export function formatDuration(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined || !Number.isFinite(seconds) || seconds < 0) return "--:--";
  const total = Math.round(seconds);
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  const ss = String(s).padStart(2, "0");
  return h > 0 ? `${h}:${String(m).padStart(2, "0")}:${ss}` : `${m}:${ss}`;
}

/** Seconds with one decimal, for clip lengths: 2.5s */
export function formatSeconds(seconds: number): string {
  if (!Number.isFinite(seconds)) return "-";
  return `${seconds.toFixed(seconds < 10 ? 1 : 0)}s`;
}

export function formatBytes(bytes: number | null | undefined): string {
  if (bytes === null || bytes === undefined || !Number.isFinite(bytes) || bytes < 0) return "-";
  if (bytes < 1024) return `${bytes} B`;
  const units = ["KB", "MB", "GB", "TB"];
  let v = bytes / 1024;
  let i = 0;
  while (v >= 1024 && i < units.length - 1) {
    v /= 1024;
    i++;
  }
  return `${v.toFixed(v < 10 ? 1 : 0)} ${units[i]}`;
}

export function formatEta(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined || !Number.isFinite(seconds)) return "estimating…";
  if (seconds <= 0) return "almost done";
  if (seconds < 60) return `~${Math.max(1, Math.round(seconds))}s left`;
  const m = Math.floor(seconds / 60);
  const s = Math.round(seconds % 60);
  return s ? `~${m}m ${s}s left` : `~${m}m left`;
}

export function formatResolution(w?: number | null, h?: number | null): string {
  if (!w || !h) return "-";
  return `${w}×${h}`;
}

export const FORMAT_LABELS: Record<string, string> = {
  mp4_h264: "MP4 (H.264)",
  mp4_h265: "MP4 (H.265/HEVC)",
  webm_vp9: "WebM (VP9)",
  png: "PNG",
  jpeg: "JPEG",
};

export function formatLabel(fmt: string): string {
  return FORMAT_LABELS[fmt] ?? fmt.toUpperCase();
}

export function formatDate(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

export function timeAgo(iso: string, now: number = Date.now()): string {
  const t = new Date(iso).getTime();
  if (Number.isNaN(t)) return "";
  const s = Math.max(0, Math.round((now - t) / 1000));
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return `${Math.floor(s / 86400)}d ago`;
}

export function titleCase(s: string): string {
  return s.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

export function clamp(v: number, lo: number, hi: number): number {
  return Math.min(hi, Math.max(lo, v));
}

export function uid(): string {
  const a = new Uint8Array(5);
  crypto.getRandomValues(a);
  return Array.from(a, (b) => b.toString(16).padStart(2, "0")).join("");
}
