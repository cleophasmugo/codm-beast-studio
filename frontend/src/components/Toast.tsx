import { AnimatePresence, motion } from "framer-motion";
import { AlertTriangle, CheckCircle2, X } from "lucide-react";
import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";

interface ToastItem {
  id: number;
  tone: "success" | "error";
  text: string;
}

interface ToastApi {
  success: (text: string) => void;
  error: (text: string) => void;
}

const Ctx = createContext<ToastApi>({ success: () => {}, error: () => {} });

export function useToast(): ToastApi {
  return useContext(Ctx);
}

let next = 1;

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([]);
  const remove = useCallback((id: number) => setItems((l) => l.filter((t) => t.id !== id)), []);
  const push = useCallback(
    (tone: ToastItem["tone"], text: string) => {
      const id = next++;
      setItems((l) => [...l.slice(-3), { id, tone, text }]);
      setTimeout(() => remove(id), tone === "error" ? 7000 : 3500);
    },
    [remove],
  );
  const api = useMemo<ToastApi>(
    () => ({ success: (t) => push("success", t), error: (t) => push("error", t) }),
    [push],
  );
  return (
    <Ctx.Provider value={api}>
      {children}
      <div
        aria-live="polite"
        className="pointer-events-none fixed inset-x-3 bottom-20 z-[60] flex flex-col items-center gap-2 lg:bottom-6 lg:left-auto lg:right-6 lg:items-end"
      >
        <AnimatePresence>
          {items.map((t) => (
            <motion.div
              key={t.id}
              layout
              initial={{ opacity: 0, y: 16, scale: 0.96 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: 8 }}
              role={t.tone === "error" ? "alert" : "status"}
              className={`pointer-events-auto flex w-full max-w-sm items-start gap-2.5 rounded-xl border px-3.5 py-3 text-sm shadow-2xl backdrop-blur ${
                t.tone === "error"
                  ? "border-rose-500/50 bg-ink-850/95 text-rose-100"
                  : "border-lime-400/40 bg-ink-850/95 text-ink-100"
              }`}
            >
              {t.tone === "error" ? (
                <AlertTriangle className="mt-0.5 size-4 shrink-0 text-rose-400" aria-hidden />
              ) : (
                <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-toxic" aria-hidden />
              )}
              <span className="min-w-0 flex-1 break-words">{t.text}</span>
              <button aria-label="Dismiss" className="text-ink-400 hover:text-white" onClick={() => remove(t.id)}>
                <X className="size-4" />
              </button>
            </motion.div>
          ))}
        </AnimatePresence>
      </div>
    </Ctx.Provider>
  );
}
