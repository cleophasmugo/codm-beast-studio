import { motion } from "framer-motion";
import { Check, Crown, Film, Gamepad2, Images, Smartphone, Sparkles, Trophy, Waves, Youtube, Zap } from "lucide-react";
import type { ReactNode } from "react";
import type { Preset, PresetName } from "../api";
import { cx } from "./ui";

const LOOK: Record<PresetName, { icon: ReactNode; grad: string }> = {
  beast: { icon: <Zap className="size-5" />, grad: "from-rose-500/30 via-orange-500/15 to-transparent" },
  cinematic: { icon: <Film className="size-5" />, grad: "from-amber-400/25 via-orange-400/10 to-transparent" },
  esports: { icon: <Trophy className="size-5" />, grad: "from-sky-400/25 via-blue-500/10 to-transparent" },
  smooth: { icon: <Waves className="size-5" />, grad: "from-teal-300/25 via-cyan-400/10 to-transparent" },
  neon: { icon: <Sparkles className="size-5" />, grad: "from-fuchsia-500/30 via-violet-500/15 to-transparent" },
  tiktok: { icon: <Smartphone className="size-5" />, grad: "from-cyan-400/25 via-pink-500/15 to-transparent" },
  youtube: { icon: <Youtube className="size-5" />, grad: "from-red-500/25 via-red-400/10 to-transparent" },
  shorts: { icon: <Gamepad2 className="size-5" />, grad: "from-lime-400/25 via-emerald-400/10 to-transparent" },
  showcase: { icon: <Images className="size-5" />, grad: "from-violet-400/25 via-indigo-400/10 to-transparent" },
};

export function presetIcon(id: PresetName): ReactNode {
  return LOOK[id]?.icon ?? <Crown className="size-5" />;
}

export function PresetPicker({
  presets,
  value,
  onChange,
  compact,
}: {
  presets: Preset[];
  value: PresetName;
  onChange: (id: PresetName) => void;
  compact?: boolean;
}) {
  return (
    <div
      role="radiogroup"
      aria-label="Montage style preset"
      className={cx("grid gap-3", compact ? "grid-cols-2 sm:grid-cols-3" : "grid-cols-1 sm:grid-cols-2 xl:grid-cols-3")}
    >
      {presets.map((p) => {
        const active = p.id === value;
        const look = LOOK[p.id] ?? { icon: <Crown className="size-5" />, grad: "from-white/10 to-transparent" };
        return (
          <motion.button
            key={p.id}
            type="button"
            role="radio"
            aria-checked={active}
            onClick={() => onChange(p.id)}
            whileHover={{ y: -2 }}
            whileTap={{ scale: 0.98 }}
            className={cx(
              "relative overflow-hidden rounded-xl border p-3.5 text-left transition-colors",
              active
                ? "border-cyber/70 bg-ink-800 shadow-[0_0_24px_-8px_rgb(34_211_238/0.9)]"
                : "border-white/[0.08] bg-ink-900/60 hover:border-white/20",
            )}
          >
            <div className={cx("pointer-events-none absolute inset-0 bg-gradient-to-br", look.grad)} />
            <div className="relative flex items-start gap-3">
              <span className={cx("size-9 shrink-0 place-items-center rounded-lg bg-black/30", compact ? "hidden sm:grid" : "grid", active ? "text-cyber" : "text-ink-200")}>
                {look.icon}
              </span>
              <div className="min-w-0 flex-1">
                <div className="flex items-start gap-2">
                  <span className={cx("text-sm font-bold text-white", compact ? "leading-tight break-words" : "truncate")}>{p.label}</span>
                  {active && <Check className="size-4 shrink-0 text-toxic" aria-hidden />}
                </div>
                <div className="mt-0.5 flex gap-1.5 text-[11px] font-semibold text-ink-300">
                  <span>{p.aspect}</span>
                  <span aria-hidden>·</span>
                  <span>{p.target_duration ? `${p.target_duration}s` : "Auto length"}</span>
                </div>
                {!compact && <p className="mt-1.5 line-clamp-2 text-xs leading-snug text-ink-300">{p.description}</p>}
              </div>
            </div>
          </motion.button>
        );
      })}
    </div>
  );
}
