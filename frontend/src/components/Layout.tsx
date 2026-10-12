import { AnimatePresence, motion } from "framer-motion";
import {
  Clapperboard,
  FolderOpen,
  History,
  ImageIcon,
  LayoutDashboard,
  Library,
  Menu,
  Music,
  Settings,
  Sparkles,
  Wand2,
  X,
} from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import { navigate, useLocation } from "../lib/router";
import { cx } from "./ui";

export interface NavItem {
  to: string;
  label: string;
  icon: ReactNode;
  short?: string;
}

const iconCls = "size-[18px]";
export const NAV: NavItem[] = [
  { to: "/", label: "Dashboard", short: "Home", icon: <LayoutDashboard className={iconCls} /> },
  { to: "/auto-edit", label: "Auto Edit", icon: <Wand2 className={iconCls} /> },
  { to: "/image-studio", label: "Image Studio", short: "Images", icon: <ImageIcon className={iconCls} /> },
  { to: "/audio", label: "Music and Audio", short: "Audio", icon: <Music className={iconCls} /> },
  { to: "/effects", label: "Effects and Filters", short: "Effects", icon: <Sparkles className={iconCls} /> },
  { to: "/projects", label: "My Projects", short: "Projects", icon: <FolderOpen className={iconCls} /> },
  { to: "/library", label: "Media Library", short: "Library", icon: <Library className={iconCls} /> },
  { to: "/exports", label: "Export History", short: "Exports", icon: <History className={iconCls} /> },
  { to: "/settings", label: "Settings", icon: <Settings className={iconCls} /> },
];

const MOBILE_PRIMARY = ["/", "/auto-edit", "/image-studio", "/projects"];

function isActivePath(current: string, to: string): boolean {
  return to === "/" ? current === "/" : current === to || current.startsWith(`${to}/`);
}

function Link({ item, current, onNavigate, compact }: { item: NavItem; current: string; onNavigate?: () => void; compact?: boolean }) {
  const active = isActivePath(current, item.to);
  return (
    <a
      href={item.to}
      aria-current={active ? "page" : undefined}
      onClick={(e) => {
        if (e.metaKey || e.ctrlKey || e.shiftKey || e.button !== 0) return;
        e.preventDefault();
        navigate(item.to);
        onNavigate?.();
      }}
      className={cx(
        "group relative flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium transition-colors",
        compact && "flex-col gap-1 px-1 py-1.5 text-[10px]",
        active ? "text-white" : "text-ink-300 hover:bg-white/[0.04] hover:text-white",
      )}
    >
      {active && (
        <motion.span
          layoutId={compact ? "nav-active-m" : "nav-active"}
          className="absolute inset-0 rounded-xl border border-cyber/30 bg-gradient-to-r from-cyber/15 to-volt/10 shadow-[0_0_20px_-8px_rgb(34_211_238/0.8)]"
          transition={{ type: "spring", stiffness: 400, damping: 34 }}
        />
      )}
      <span className={cx("relative", active ? "text-cyber" : "text-ink-400 group-hover:text-ink-200")}>{item.icon}</span>
      <span className="relative truncate">{compact ? (item.short ?? item.label) : item.label}</span>
    </a>
  );
}

function Brand() {
  return (
    <a
      href="/"
      onClick={(e) => {
        e.preventDefault();
        navigate("/");
      }}
      className="flex items-center gap-2.5 rounded-lg"
    >
      <span className="grid size-9 place-items-center rounded-xl bg-gradient-to-br from-cyber to-volt shadow-[0_0_20px_-4px_rgb(139_92_246/0.9)]">
        <Clapperboard className="size-5 text-white" aria-hidden />
      </span>
      <span className="leading-tight">
        <span className="block text-sm font-extrabold tracking-wide text-white">CODM BEAST</span>
        <span className="block text-[10px] font-semibold tracking-[0.25em] text-cyber">STUDIO</span>
      </span>
    </a>
  );
}

export function Layout({ children }: { children: ReactNode }) {
  const { path } = useLocation();
  const [drawer, setDrawer] = useState(false);
  useEffect(() => setDrawer(false), [path]);

  return (
    <div className="min-h-dvh">
      <a
        href="#main"
        className="sr-only z-[70] rounded-lg bg-cyber px-3 py-2 font-semibold text-ink-950 focus:not-sr-only focus:fixed focus:top-3 focus:left-3"
      >
        Skip to content
      </a>

      {/* desktop sidebar */}
      <aside className="fixed inset-y-0 left-0 z-30 hidden w-60 flex-col border-r border-white/[0.06] bg-ink-900/80 px-3 py-5 backdrop-blur-xl lg:flex">
        <div className="px-2">
          <Brand />
        </div>
        <nav aria-label="Main" className="mt-8 flex flex-1 flex-col gap-1">
          {NAV.map((n) => (
            <Link key={n.to} item={n} current={path} />
          ))}
        </nav>
        <p className="px-3 text-[11px] leading-relaxed text-ink-400">
          Highlights are found from motion, sound and flashes. Always review before posting.
        </p>
      </aside>

      {/* mobile / tablet top bar */}
      <header className="sticky top-0 z-30 flex h-14 items-center justify-between border-b border-white/[0.06] bg-ink-900/85 px-4 backdrop-blur-xl lg:hidden">
        <Brand />
        <button
          type="button"
          aria-label="Open menu"
          aria-expanded={drawer}
          onClick={() => setDrawer(true)}
          className="grid size-10 place-items-center rounded-lg text-ink-200 hover:bg-white/5"
        >
          <Menu className="size-5" />
        </button>
      </header>

      <AnimatePresence>
        {drawer && (
          <motion.div className="fixed inset-0 z-50 lg:hidden" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
            <div className="absolute inset-0 bg-black/70 backdrop-blur-sm" onClick={() => setDrawer(false)} />
            <motion.nav
              aria-label="Main"
              initial={{ x: "100%" }}
              animate={{ x: 0 }}
              exit={{ x: "100%" }}
              transition={{ type: "spring", stiffness: 380, damping: 36 }}
              className="absolute inset-y-0 right-0 flex w-72 max-w-[85vw] flex-col gap-1 border-l border-white/10 bg-ink-900 p-4"
            >
              <div className="mb-4 flex items-center justify-between">
                <span className="text-sm font-bold text-ink-200">Menu</span>
                <button
                  type="button"
                  aria-label="Close menu"
                  onClick={() => setDrawer(false)}
                  className="grid size-9 place-items-center rounded-lg text-ink-300 hover:bg-white/5"
                >
                  <X className="size-5" />
                </button>
              </div>
              {NAV.map((n) => (
                <Link key={n.to} item={n} current={path} onNavigate={() => setDrawer(false)} />
              ))}
            </motion.nav>
          </motion.div>
        )}
      </AnimatePresence>

      <main id="main" className="px-4 pt-5 pb-28 sm:px-6 lg:ml-60 lg:px-8 lg:pt-8 lg:pb-12">
        <div className="mx-auto w-full max-w-7xl min-w-0">{children}</div>
      </main>

      {/* mobile bottom nav */}
      <nav
        aria-label="Quick"
        className="fixed inset-x-0 bottom-0 z-30 grid grid-cols-5 gap-1 border-t border-white/[0.06] bg-ink-900/90 px-2 pt-1.5 pb-[max(0.375rem,env(safe-area-inset-bottom))] backdrop-blur-xl lg:hidden"
      >
        {NAV.filter((n) => MOBILE_PRIMARY.includes(n.to)).map((n) => (
          <Link key={n.to} item={n} current={path} compact />
        ))}
        <button
          type="button"
          onClick={() => setDrawer(true)}
          className="flex flex-col items-center gap-1 rounded-xl px-1 py-1.5 text-[10px] font-medium text-ink-300 hover:text-white"
        >
          <Menu className="size-[18px] text-ink-400" aria-hidden />
          More
        </button>
      </nav>
    </div>
  );
}
