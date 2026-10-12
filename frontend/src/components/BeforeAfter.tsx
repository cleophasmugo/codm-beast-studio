import { useId, useState } from "react";

/** Draggable before/after comparison of two images of the same size. */
export function BeforeAfter({
  before,
  after,
  beforeLabel = "Before",
  afterLabel = "After",
  alt = "Comparison",
}: {
  before: string;
  after: string;
  beforeLabel?: string;
  afterLabel?: string;
  alt?: string;
}) {
  const [pos, setPos] = useState(50);
  const id = useId();
  return (
    <div className="space-y-2">
      <div className="relative overflow-hidden rounded-xl border border-white/10 bg-black select-none" data-testid="before-after">
        <img src={after} alt={`${alt} (after)`} className="block w-full" draggable={false} />
        <div className="absolute inset-0 overflow-hidden" style={{ clipPath: `inset(0 ${100 - pos}% 0 0)` }}>
          <img src={before} alt={`${alt} (before)`} className="block w-full" draggable={false} />
        </div>
        <div className="pointer-events-none absolute inset-y-0 w-0.5 bg-cyber shadow-[0_0_12px_#22d3ee]" style={{ left: `${pos}%` }} />
        <span className="absolute top-2 left-2 rounded bg-black/70 px-2 py-0.5 text-[11px] font-bold text-white">{beforeLabel}</span>
        <span className="absolute top-2 right-2 rounded bg-cyber/85 px-2 py-0.5 text-[11px] font-bold text-ink-950">{afterLabel}</span>
      </div>
      <label htmlFor={id} className="sr-only">
        Comparison position
      </label>
      <input id={id} type="range" min={0} max={100} value={pos} onChange={(e) => setPos(Number(e.target.value))} className="w-full" />
    </div>
  );
}
