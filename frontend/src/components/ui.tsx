import { AnimatePresence, motion } from "framer-motion";
import { AlertTriangle, Info, Loader2, X } from "lucide-react";
import {
  forwardRef,
  useEffect,
  useId,
  useRef,
  type ButtonHTMLAttributes,
  type ReactNode,
  type SelectHTMLAttributes,
} from "react";

export function cx(...parts: (string | false | null | undefined)[]): string {
  return parts.filter(Boolean).join(" ");
}

// ----------------------------------------------------------------------------- button
type Variant = "primary" | "secondary" | "ghost" | "danger" | "success";
type Size = "sm" | "md" | "lg";

const variants: Record<Variant, string> = {
  primary:
    "text-white bg-gradient-to-r from-electric via-volt to-volt shadow-[0_0_24px_-6px_rgb(139_92_246/0.8)] hover:shadow-[0_0_32px_-4px_rgb(34_211_238/0.7)] hover:brightness-110",
  secondary: "text-ink-100 bg-ink-700 border border-white/10 hover:bg-ink-600 hover:border-cyber/40",
  ghost: "text-ink-200 hover:bg-white/5 hover:text-white",
  danger: "text-rose-100 bg-rose-600/20 border border-rose-500/40 hover:bg-rose-600/35",
  success:
    "text-ink-950 bg-toxic hover:brightness-110 shadow-[0_0_24px_-6px_rgb(163_230_53/0.8)]",
};
const sizes: Record<Size, string> = {
  sm: "h-8 px-3 text-xs gap-1.5",
  md: "h-10 px-4 text-sm gap-2",
  lg: "h-12 px-6 text-base gap-2.5",
};

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  loading?: boolean;
  icon?: ReactNode;
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { variant = "secondary", size = "md", loading, icon, className, children, disabled, type = "button", ...rest },
  ref,
) {
  return (
    <button
      ref={ref}
      type={type}
      disabled={disabled || loading}
      className={cx(
        "inline-flex shrink-0 items-center justify-center rounded-lg font-semibold whitespace-nowrap transition-all duration-150",
        "disabled:cursor-not-allowed disabled:opacity-45 disabled:shadow-none disabled:hover:brightness-100",
        variants[variant],
        sizes[size],
        className,
      )}
      {...rest}
    >
      {loading ? <Loader2 className="size-4 animate-spin" aria-hidden /> : icon}
      {children}
    </button>
  );
});

export function IconButton({
  label,
  children,
  className,
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & { label: string }) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      className={cx(
        "inline-flex size-8 shrink-0 items-center justify-center rounded-lg text-ink-300 transition hover:bg-white/10 hover:text-white disabled:opacity-35 disabled:hover:bg-transparent",
        className,
      )}
      {...rest}
    >
      {children}
    </button>
  );
}

// ----------------------------------------------------------------------------- layout
export function Card({
  children,
  className,
  glow,
  as: Tag = "section",
}: {
  children: ReactNode;
  className?: string;
  glow?: boolean;
  as?: "section" | "div" | "article";
}) {
  return <Tag className={cx("panel p-4 sm:p-5", glow && "glow-border", className)}>{children}</Tag>;
}

export function CardTitle({ icon, children, action }: { icon?: ReactNode; children: ReactNode; action?: ReactNode }) {
  return (
    <div className="mb-4 flex items-center justify-between gap-3">
      <h2 className="flex min-w-0 items-center gap-2 text-sm font-bold tracking-wide text-ink-100 uppercase">
        {icon && <span className="text-cyber">{icon}</span>}
        <span className="truncate">{children}</span>
      </h2>
      {action}
    </div>
  );
}

export function PageHeader({ title, subtitle, actions }: { title: string; subtitle?: ReactNode; actions?: ReactNode }) {
  return (
    <header className="mb-6 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
      <div className="min-w-0">
        <h1 className="font-display text-2xl font-extrabold tracking-tight text-white sm:text-3xl">{title}</h1>
        {subtitle && <p className="mt-1 max-w-2xl text-sm text-ink-300">{subtitle}</p>}
      </div>
      {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
    </header>
  );
}

export function Badge({
  children,
  tone = "default",
  className,
}: {
  children: ReactNode;
  tone?: "default" | "cyan" | "violet" | "green" | "amber" | "red" | "blue";
  className?: string;
}) {
  const tones = {
    default: "bg-white/5 text-ink-200 border-white/10",
    cyan: "bg-cyan-400/10 text-cyan-300 border-cyan-400/30",
    violet: "bg-violet-500/10 text-violet-300 border-violet-400/30",
    green: "bg-lime-400/10 text-lime-300 border-lime-400/30",
    amber: "bg-amber-400/10 text-amber-300 border-amber-400/30",
    red: "bg-rose-500/10 text-rose-300 border-rose-400/30",
    blue: "bg-blue-500/10 text-blue-300 border-blue-400/30",
  } as const;
  return (
    <span
      className={cx(
        "inline-flex items-center gap-1 rounded-md border px-1.5 py-0.5 text-[11px] font-semibold whitespace-nowrap",
        tones[tone],
        className,
      )}
    >
      {children}
    </span>
  );
}

export function Spinner({ label = "Loading" }: { label?: string }) {
  return (
    <div role="status" className="flex items-center gap-2 py-6 text-sm text-ink-300">
      <Loader2 className="size-4 animate-spin text-cyber" aria-hidden />
      {label}…
    </div>
  );
}

export function ErrorBanner({ children, onRetry }: { children: ReactNode; onRetry?: () => void }) {
  if (!children) return null;
  return (
    <div
      role="alert"
      className="flex items-start gap-3 rounded-xl border border-rose-500/40 bg-rose-500/10 px-4 py-3 text-sm text-rose-100"
    >
      <AlertTriangle className="mt-0.5 size-4 shrink-0 text-rose-400" aria-hidden />
      <div className="min-w-0 flex-1 break-words">{children}</div>
      {onRetry && (
        <Button size="sm" variant="ghost" onClick={onRetry}>
          Retry
        </Button>
      )}
    </div>
  );
}

export function Note({ children, tone = "info" }: { children: ReactNode; tone?: "info" | "warn" }) {
  return (
    <div
      className={cx(
        "flex items-start gap-2.5 rounded-xl border px-3.5 py-2.5 text-xs leading-relaxed",
        tone === "info" ? "border-cyber/25 bg-cyber/5 text-ink-200" : "border-amber-400/30 bg-amber-400/5 text-amber-100",
      )}
    >
      <Info className={cx("mt-0.5 size-3.5 shrink-0", tone === "info" ? "text-cyber" : "text-amber-300")} aria-hidden />
      <div className="min-w-0">{children}</div>
    </div>
  );
}

export function Empty({ icon, title, children }: { icon?: ReactNode; title: string; children?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center rounded-xl border border-dashed border-white/10 px-6 py-10 text-center">
      {icon && <div className="mb-3 text-ink-400">{icon}</div>}
      <p className="font-semibold text-ink-200">{title}</p>
      {children && <div className="mt-1 text-sm text-ink-400">{children}</div>}
    </div>
  );
}

export function ProgressBar({ value, tone = "brand", label }: { value: number; tone?: "brand" | "red" | "green"; label?: string }) {
  const pct = Math.round(Math.min(1, Math.max(0, value)) * 100);
  const fill = {
    brand: "from-cyber via-electric to-volt",
    red: "from-rose-500 to-rose-400",
    green: "from-lime-400 to-emerald-400",
  }[tone];
  return (
    <div
      role="progressbar"
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={pct}
      aria-label={label ?? "Progress"}
      className="h-2.5 w-full overflow-hidden rounded-full bg-ink-700"
    >
      <motion.div
        className={cx("h-full rounded-full bg-gradient-to-r", fill)}
        initial={false}
        animate={{ width: `${pct}%` }}
        transition={{ type: "spring", stiffness: 120, damping: 24 }}
        style={{ boxShadow: "0 0 12px rgb(34 211 238 / 0.6)" }}
      />
    </div>
  );
}

// ----------------------------------------------------------------------------- form controls
export function Toggle({
  checked,
  onChange,
  label,
  description,
  disabled,
}: {
  checked: boolean;
  onChange: (v: boolean) => void;
  label: string;
  description?: string;
  disabled?: boolean;
}) {
  const id = useId();
  return (
    <div className="flex items-center justify-between gap-3 py-1.5">
      <label htmlFor={id} className="min-w-0 cursor-pointer">
        <span className="block text-sm font-medium text-ink-100">{label}</span>
        {description && <span className="block text-xs text-ink-400">{description}</span>}
      </label>
      <button
        id={id}
        type="button"
        role="switch"
        aria-checked={checked}
        disabled={disabled}
        onClick={() => onChange(!checked)}
        className={cx(
          "relative inline-flex h-6 w-11 shrink-0 items-center rounded-full border transition-colors disabled:opacity-40",
          checked ? "border-toxic/60 bg-toxic/80" : "border-white/10 bg-ink-600",
        )}
      >
        <span
          className={cx(
            "inline-block size-4.5 rounded-full bg-white shadow transition-transform",
            checked ? "translate-x-[22px]" : "translate-x-[3px]",
          )}
        />
      </button>
    </div>
  );
}

export function Slider({
  label,
  value,
  min,
  max,
  step = 0.01,
  onChange,
  format,
  disabled,
  suffix,
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  step?: number;
  onChange: (v: number) => void;
  format?: (v: number) => string;
  disabled?: boolean;
  suffix?: ReactNode;
}) {
  const id = useId();
  return (
    <div className="py-1">
      <div className="mb-1 flex items-center justify-between gap-2">
        <label htmlFor={id} className="text-xs font-medium text-ink-200">
          {label}
        </label>
        <span className="flex items-center gap-2 font-mono text-xs text-cyber">
          {format ? format(value) : value.toFixed(2)}
          {suffix}
        </span>
      </div>
      <input
        id={id}
        type="range"
        className="w-full"
        min={min}
        max={max}
        step={step}
        value={value}
        disabled={disabled}
        onChange={(e) => onChange(Number(e.target.value))}
      />
    </div>
  );
}

export function SelectField({
  label,
  children,
  className,
  ...rest
}: SelectHTMLAttributes<HTMLSelectElement> & { label: string }) {
  const id = useId();
  return (
    <div className={className}>
      <label htmlFor={id} className="label">
        {label}
      </label>
      <select id={id} className="field" {...rest}>
        {children}
      </select>
    </div>
  );
}

export function TextField({
  label,
  value,
  onChange,
  placeholder,
  maxLength,
  type = "text",
  className,
  hint,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  maxLength?: number;
  type?: string;
  className?: string;
  hint?: ReactNode;
}) {
  const id = useId();
  return (
    <div className={className}>
      <label htmlFor={id} className="label">
        {label}
      </label>
      <input
        id={id}
        type={type}
        className="field"
        value={value}
        placeholder={placeholder}
        maxLength={maxLength}
        onChange={(e) => onChange(e.target.value)}
      />
      {hint && <p className="mt-1 text-xs text-ink-400">{hint}</p>}
    </div>
  );
}

export function NumberField({
  label,
  value,
  onChange,
  min,
  max,
  step = 0.1,
  className,
}: {
  label: string;
  value: number;
  onChange: (v: number) => void;
  min?: number;
  max?: number;
  step?: number;
  className?: string;
}) {
  const id = useId();
  return (
    <div className={className}>
      <label htmlFor={id} className="label">
        {label}
      </label>
      <input
        id={id}
        type="number"
        className="field font-mono"
        value={Number.isFinite(value) ? Number(value.toFixed(3)) : 0}
        min={min}
        max={max}
        step={step}
        onChange={(e) => {
          const v = Number(e.target.value);
          if (Number.isFinite(v)) onChange(v);
        }}
      />
    </div>
  );
}

/** Pill-style single choice. */
export function Segmented<T extends string | number>({
  label,
  options,
  value,
  onChange,
  disabledOptions = [],
}: {
  label: string;
  options: { value: T; label: string; title?: string }[];
  value: T;
  onChange: (v: T) => void;
  disabledOptions?: T[];
}) {
  return (
    <fieldset>
      <legend className="label">{label}</legend>
      <div className="flex flex-wrap gap-1.5">
        {options.map((o) => {
          const active = o.value === value;
          const disabled = disabledOptions.includes(o.value);
          return (
            <button
              key={String(o.value)}
              type="button"
              aria-pressed={active}
              disabled={disabled}
              title={o.title}
              onClick={() => onChange(o.value)}
              className={cx(
                "h-8 rounded-lg border px-3 text-xs font-semibold transition disabled:cursor-not-allowed disabled:opacity-35",
                active
                  ? "border-cyber/70 bg-cyber/15 text-cyan-200 shadow-[0_0_14px_-4px_rgb(34_211_238/0.8)]"
                  : "border-white/10 bg-ink-800 text-ink-200 hover:border-white/25",
              )}
            >
              {o.label}
            </button>
          );
        })}
      </div>
    </fieldset>
  );
}

// ----------------------------------------------------------------------------- modal
export function Modal({
  open,
  onClose,
  title,
  children,
  wide,
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  children: ReactNode;
  wide?: boolean;
}) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const prev = document.activeElement as HTMLElement | null;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    setTimeout(() => ref.current?.focus(), 0);
    return () => {
      window.removeEventListener("keydown", onKey);
      prev?.focus?.();
    };
  }, [open, onClose]);
  return (
    <AnimatePresence>
      {open && (
        <motion.div
          className="fixed inset-0 z-50 flex items-end justify-center bg-black/70 p-0 backdrop-blur-sm sm:items-center sm:p-6"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          onMouseDown={(e) => e.target === e.currentTarget && onClose()}
        >
          <motion.div
            ref={ref}
            role="dialog"
            aria-modal="true"
            aria-label={title}
            tabIndex={-1}
            initial={{ y: 24, opacity: 0, scale: 0.98 }}
            animate={{ y: 0, opacity: 1, scale: 1 }}
            exit={{ y: 24, opacity: 0 }}
            transition={{ type: "spring", stiffness: 300, damping: 28 }}
            className={cx(
              "panel glow-border max-h-[92dvh] w-full overflow-y-auto rounded-b-none p-5 focus:outline-none sm:rounded-2xl",
              wide ? "sm:max-w-4xl" : "sm:max-w-lg",
            )}
          >
            <div className="mb-4 flex items-center justify-between gap-3">
              <h2 className="text-lg font-bold text-white">{title}</h2>
              <IconButton label="Close" onClick={onClose}>
                <X className="size-4" />
              </IconButton>
            </div>
            {children}
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

export function ConfirmDialog({
  open,
  title,
  message,
  confirmLabel = "Delete",
  onConfirm,
  onCancel,
  busy,
}: {
  open: boolean;
  title: string;
  message: ReactNode;
  confirmLabel?: string;
  onConfirm: () => void;
  onCancel: () => void;
  busy?: boolean;
}) {
  return (
    <Modal open={open} onClose={onCancel} title={title}>
      <div className="text-sm text-ink-200">{message}</div>
      <div className="mt-6 flex justify-end gap-2">
        <Button variant="ghost" onClick={onCancel}>
          Cancel
        </Button>
        <Button variant="danger" onClick={onConfirm} loading={busy}>
          {confirmLabel}
        </Button>
      </div>
    </Modal>
  );
}

export function Stat({ label, value, hint }: { label: string; value: ReactNode; hint?: ReactNode }) {
  return (
    <div className="min-w-0 rounded-xl border border-white/5 bg-ink-900/60 px-3 py-2.5">
      <div className="text-[11px] font-semibold tracking-wide text-ink-400 uppercase">{label}</div>
      <div className="mt-0.5 truncate text-lg font-bold text-white">{value}</div>
      {hint && <div className="truncate text-xs text-ink-400">{hint}</div>}
    </div>
  );
}
