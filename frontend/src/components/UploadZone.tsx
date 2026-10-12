import { AnimatePresence, motion } from "framer-motion";
import { CheckCircle2, FileVideo, UploadCloud, X } from "lucide-react";
import { useCallback, useId, useRef, useState } from "react";
import { uploadFiles, type Media } from "../api";
import { formatBytes } from "../lib/format";
import { Button, ErrorBanner, ProgressBar, cx } from "./ui";

export const ACCEPT_ALL =
  ".mp4,.mov,.mkv,.webm,.m4v,.avi,.jpg,.jpeg,.png,.webp,.gif,.bmp,.mp3,.wav,.m4a,.aac,.ogg,.flac,video/*,image/*,audio/*";

interface Batch {
  id: number;
  names: string[];
  bytes: number;
  progress: number;
  state: "uploading" | "processing" | "done" | "error";
  error?: string;
  abort?: () => void;
}

let batchId = 1;

export function UploadZone({
  onUploaded,
  accept = ACCEPT_ALL,
  title = "Drop gameplay clips, screenshots or music",
  hint = "MP4, MOV, MKV, WebM, JPG, PNG, WebP, MP3, WAV and more. Multiple files at once.",
  compact,
  folder,
}: {
  onUploaded: (media: Media[]) => void;
  accept?: string;
  title?: string;
  hint?: string;
  compact?: boolean;
  folder?: string;
}) {
  const inputId = useId();
  const inputRef = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);
  const [batches, setBatches] = useState<Batch[]>([]);

  const update = (id: number, patch: Partial<Batch>) =>
    setBatches((l) => l.map((b) => (b.id === id ? { ...b, ...patch } : b)));

  const start = useCallback(
    (files: File[]) => {
      if (!files.length) return;
      const id = batchId++;
      const handle = uploadFiles(
        files,
        (f) => update(id, { progress: f, state: f >= 1 ? "processing" : "uploading" }),
        folder,
      );
      setBatches((l) => [
        { id, names: files.map((f) => f.name), bytes: files.reduce((s, f) => s + f.size, 0), progress: 0, state: "uploading", abort: handle.abort },
        ...l.filter((b) => b.state !== "done").slice(0, 4),
      ]);
      handle.promise
        .then((media) => {
          update(id, { state: "done", progress: 1 });
          onUploaded(media);
        })
        .catch((e: unknown) => update(id, { state: "error", error: e instanceof Error ? e.message : String(e) }));
    },
    [onUploaded, folder],
  );

  return (
    <div>
      <label
        htmlFor={inputId}
        onDragOver={(e) => {
          e.preventDefault();
          setOver(true);
        }}
        onDragLeave={() => setOver(false)}
        onDrop={(e) => {
          e.preventDefault();
          setOver(false);
          start(Array.from(e.dataTransfer.files));
        }}
        data-testid="upload-zone"
        className={cx(
          "group relative flex cursor-pointer flex-col items-center justify-center overflow-hidden rounded-2xl border-2 border-dashed text-center transition-all",
          compact ? "px-4 py-6" : "px-6 py-10 sm:py-14",
          over
            ? "border-cyber bg-cyber/10 shadow-[0_0_40px_-10px_rgb(34_211_238/0.9)]"
            : "border-white/15 bg-ink-900/50 hover:border-cyber/50 hover:bg-ink-900/80",
        )}
      >
        <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(400px_160px_at_50%_0%,rgb(139_92_246/0.15),transparent)]" />
        <motion.div
          animate={over ? { y: -6, scale: 1.08 } : { y: 0, scale: 1 }}
          className={cx(
            "relative grid place-items-center rounded-2xl bg-gradient-to-br from-cyber/20 to-volt/20 text-cyber ring-1 ring-cyber/30",
            compact ? "mb-2 size-11" : "mb-4 size-16",
          )}
        >
          <UploadCloud className={compact ? "size-5" : "size-8"} aria-hidden />
        </motion.div>
        <p className={cx("relative font-bold text-white", compact ? "text-sm" : "text-lg")}>{title}</p>
        <p className="relative mt-1 max-w-md text-xs text-ink-300 sm:text-sm">{hint}</p>
        <span className="relative mt-4 inline-flex h-9 items-center rounded-lg border border-cyber/40 bg-cyber/10 px-4 text-sm font-semibold text-cyan-200 group-hover:bg-cyber/20">
          Browse files
        </span>
        <input
          ref={inputRef}
          id={inputId}
          type="file"
          multiple
          accept={accept}
          className="sr-only"
          data-testid="upload-input"
          onChange={(e) => {
            start(Array.from(e.target.files ?? []));
            e.target.value = "";
          }}
        />
      </label>

      <AnimatePresence initial={false}>
        {batches.map((b) => (
          <motion.div
            key={b.id}
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            exit={{ opacity: 0, height: 0 }}
            className="mt-3"
          >
            {b.state === "error" ? (
              <ErrorBanner>
                <strong className="font-semibold">Upload failed:</strong> {b.error}
              </ErrorBanner>
            ) : (
              <div className="rounded-xl border border-white/10 bg-ink-900/70 px-3.5 py-3">
                <div className="mb-2 flex items-center gap-2 text-sm">
                  {b.state === "done" ? (
                    <CheckCircle2 className="size-4 shrink-0 text-toxic" aria-hidden />
                  ) : (
                    <FileVideo className="size-4 shrink-0 text-cyber" aria-hidden />
                  )}
                  <span className="min-w-0 flex-1 truncate text-ink-100">
                    {b.names.length === 1 ? b.names[0] : `${b.names.length} files`}{" "}
                    <span className="text-ink-400">· {formatBytes(b.bytes)}</span>
                  </span>
                  <span className="shrink-0 text-xs text-ink-300">
                    {b.state === "uploading" && `${Math.round(b.progress * 100)}%`}
                    {b.state === "processing" && "Checking and making thumbnails…"}
                    {b.state === "done" && "Uploaded"}
                  </span>
                  {b.state === "uploading" && (
                    <Button size="sm" variant="ghost" aria-label="Cancel upload" onClick={() => b.abort?.()} icon={<X className="size-3.5" />} />
                  )}
                </div>
                <ProgressBar value={b.state === "processing" ? 1 : b.progress} tone={b.state === "done" ? "green" : "brand"} label="Upload progress" />
              </div>
            )}
          </motion.div>
        ))}
      </AnimatePresence>
    </div>
  );
}
