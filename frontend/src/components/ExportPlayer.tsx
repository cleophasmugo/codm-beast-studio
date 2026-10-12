import { Download, FolderOpen } from "lucide-react";
import { useEffect, useState } from "react";
import type { ExportItem } from "../api";
import { mediaUrl } from "../api";
import { formatBytes, formatDuration, formatLabel, formatResolution } from "../lib/format";
import { navigate } from "../lib/router";
import { Badge, Button, Note } from "./ui";

export function DownloadLink({ item, size = "md" }: { item: ExportItem; size?: "sm" | "md" }) {
  return (
    <a
      href={mediaUrl(item.download_url)}
      download={item.name}
      data-testid="download-link"
      className={`inline-flex items-center justify-center gap-2 rounded-lg bg-toxic font-semibold text-ink-950 shadow-[0_0_24px_-6px_rgb(163_230_53/0.8)] transition hover:brightness-110 ${
        size === "sm" ? "h-8 px-3 text-xs" : "h-10 px-4 text-sm"
      }`}
    >
      <Download className="size-4" aria-hidden /> Download
    </a>
  );
}

export function ExportPlayer({ item, showProjectLink = true }: { item: ExportItem; showProjectLink?: boolean }) {
  const isImage = item.kind === "image";
  const tall = item.height > item.width;
  const [playError, setPlayError] = useState<string | null>(null);
  useEffect(() => setPlayError(null), [item.id]);
  return (
    <div className="space-y-3">
      <div className="overflow-hidden rounded-xl border border-white/10 bg-black">
        {isImage ? (
          <img src={mediaUrl(item.url)} alt={item.name} className="mx-auto max-h-[70vh] w-auto object-contain" />
        ) : (
          <video
            key={item.id}
            src={mediaUrl(item.url)}
            poster={item.thumb_url ? mediaUrl(item.thumb_url) : undefined}
            controls
            playsInline
            preload="metadata"
            data-testid="export-video"
            onError={(e) => {
              const err = e.currentTarget.error;
              setPlayError(err ? `code ${err.code}` : "unknown");
            }}
            onLoadedMetadata={() => setPlayError(null)}
            className={`mx-auto block bg-black ${tall ? "max-h-[70vh] w-auto" : "aspect-video w-full"}`}
          />
        )}
      </div>
      {playError && (
        <div data-testid="video-unsupported">
          <Note tone="warn">
            This browser can't play {formatLabel(item.format)} inside the page ({playError}). The file itself is fine: download it to watch, or pick
            WebM (VP9) in the project's Output settings for in-browser playback.
          </Note>
        </div>
      )}
      <div className="flex flex-wrap items-center gap-2">
        <span className="mr-auto min-w-0 truncate text-sm font-semibold text-white">{item.name}</span>
        <Badge tone="violet">{formatLabel(item.format)}</Badge>
        <Badge>{formatResolution(item.width, item.height)}</Badge>
        {!isImage && <Badge>{formatDuration(item.duration)}</Badge>}
        <Badge>{formatBytes(item.size_bytes)}</Badge>
        {item.kind === "preview" && <Badge tone="amber">Preview quality</Badge>}
      </div>
      <div className="flex flex-wrap gap-2">
        <DownloadLink item={item} />
        {showProjectLink && item.project_id && (
          <Button variant="secondary" icon={<FolderOpen className="size-4" />} onClick={() => navigate(`/projects/${item.project_id}`)}>
            Open in editor
          </Button>
        )}
      </div>
    </div>
  );
}
