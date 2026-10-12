import { FileAudio, ImageIcon, Sticker, Video } from "lucide-react";
import { mediaUrl, type Media } from "../api";
import { formatDuration } from "../lib/format";
import { cx } from "./ui";

export function KindIcon({ kind, className = "size-4" }: { kind: string; className?: string }) {
  if (kind === "video") return <Video className={className} aria-hidden />;
  if (kind === "audio") return <FileAudio className={className} aria-hidden />;
  if (kind === "sticker") return <Sticker className={className} aria-hidden />;
  return <ImageIcon className={className} aria-hidden />;
}

export function MediaThumb({ media, className }: { media: Media; className?: string }) {
  const dur = media.info.duration;
  return (
    <div className={cx("relative aspect-video overflow-hidden rounded-lg bg-ink-800", media.kind === "sticker" && "checker", className)}>
      {media.thumb_url ? (
        <img
          src={mediaUrl(media.thumb_url)}
          alt=""
          loading="lazy"
          className={cx("size-full", media.kind === "sticker" || media.kind === "audio" ? "object-contain p-1" : "object-cover")}
        />
      ) : (
        <div className="grid size-full place-items-center text-ink-400">
          <KindIcon kind={media.kind} className="size-6" />
        </div>
      )}
      <span className="absolute top-1.5 left-1.5 inline-flex items-center gap-1 rounded-md bg-black/70 px-1.5 py-0.5 text-[10px] font-bold text-white uppercase">
        <KindIcon kind={media.kind} className="size-3" />
        {media.kind === "image" ? "shot" : media.kind}
      </span>
      {typeof dur === "number" && dur > 0 && (
        <span className="absolute right-1.5 bottom-1.5 rounded-md bg-black/75 px-1.5 py-0.5 font-mono text-[10px] text-white">
          {formatDuration(dur)}
        </span>
      )}
    </div>
  );
}
