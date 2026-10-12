import { CheckCircle2 } from "lucide-react";
import type { Media } from "../api";
import { MediaThumb } from "./MediaThumb";
import { Empty, cx } from "./ui";

/** Multi-select grid of media (e.g. gameplay videos + screenshots). */
export function MediaPicker({
  media,
  selected,
  onToggle,
  emptyText = "Nothing here yet. Upload some gameplay first.",
  single,
}: {
  media: Media[];
  selected: string[];
  onToggle: (id: string) => void;
  emptyText?: string;
  single?: boolean;
}) {
  if (!media.length) return <Empty title="No media">{emptyText}</Empty>;
  return (
    <ul className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4" role="listbox" aria-multiselectable={!single} aria-label="Media">
      {media.map((m) => {
        const on = selected.includes(m.id);
        return (
          <li key={m.id} role="option" aria-selected={on}>
            <button
              type="button"
              onClick={() => onToggle(m.id)}
              data-testid={`pick-${m.id}`}
              className={cx(
                "group relative block w-full rounded-xl border p-1.5 text-left transition",
                on ? "border-toxic/70 bg-toxic/10 shadow-[0_0_20px_-8px_rgb(163_230_53/0.9)]" : "border-white/[0.08] bg-ink-900/60 hover:border-white/25",
              )}
            >
              <MediaThumb media={m} />
              <span className="mt-1.5 block truncate px-0.5 text-xs font-semibold text-ink-100">{m.name}</span>
              {on && (
                <CheckCircle2 className="absolute top-3 right-3 size-5 rounded-full bg-ink-950 text-toxic" aria-hidden />
              )}
            </button>
          </li>
        );
      })}
    </ul>
  );
}
