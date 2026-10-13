import type { ReactNode } from "react";
import { mediaUrl, type Media } from "../api";
import { formatBytes, formatDuration } from "../lib/format";
import { Badge, cx } from "./ui";

/** One audio track: waveform thumbnail, player and license text. */
export function AudioRow({
  media,
  selected,
  onSelect,
  actions,
}: {
  media: Media;
  selected?: boolean;
  onSelect?: () => void;
  actions?: ReactNode;
}) {
  return (
    <div
      className={cx(
        "rounded-xl border p-3 transition",
        selected ? "border-toxic/60 bg-toxic/[0.06]" : "border-white/[0.08] bg-ink-900/60",
      )}
    >
      <div className="flex flex-wrap items-center gap-2">
        {onSelect && (
          <input
            type="radio"
            name="music-track"
            aria-label={`Use ${media.name}`}
            checked={!!selected}
            onChange={onSelect}
            className="size-4 accent-[#a3e635]"
          />
        )}
        <span className="min-w-0 flex-1 truncate font-semibold text-white">{media.name}</span>
        <Badge tone={media.source === "library" ? "violet" : media.source === "online" ? "green" : "cyan"}>
          {media.source === "library" ? "Library" : media.source === "online" ? "Online" : "Upload"}
        </Badge>
        <Badge>{formatDuration(media.info.duration)}</Badge>
        <Badge>{formatBytes(media.size_bytes)}</Badge>
        {actions}
      </div>
      {media.thumb_url && (
        <img src={mediaUrl(media.thumb_url)} alt="" className="mt-2 h-10 w-full rounded-md bg-ink-950 object-fill opacity-90" loading="lazy" />
      )}
      <audio controls preload="none" src={mediaUrl(media.url)} className="mt-2 h-9 w-full" aria-label={`Preview ${media.name}`} />
      <p className="mt-1.5 text-[11px] leading-snug text-ink-400">
        <span className="font-semibold text-ink-300">License: </span>
        {media.license || "Your upload. Make sure you have the rights to use this music before posting."}
      </p>
    </div>
  );
}
