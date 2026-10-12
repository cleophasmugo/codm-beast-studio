/** Tiny history-API router (the backend has SPA fallback, so deep links work). */
import { useSyncExternalStore } from "react";

const listeners = new Set<() => void>();
const emit = () => listeners.forEach((l) => l());

if (typeof window !== "undefined") window.addEventListener("popstate", emit);

function subscribe(cb: () => void) {
  listeners.add(cb);
  return () => listeners.delete(cb);
}

const snapshot = () => window.location.pathname + window.location.search;

export function navigate(to: string, opts: { replace?: boolean } = {}): void {
  if (to === snapshot()) return;
  if (opts.replace) window.history.replaceState(null, "", to);
  else window.history.pushState(null, "", to);
  emit();
  if (!opts.replace) window.scrollTo({ top: 0 });
}

export function useLocation(): { path: string; query: URLSearchParams } {
  const loc = useSyncExternalStore(subscribe, snapshot, () => "/");
  const [path, search = ""] = loc.split("?");
  return { path: path.replace(/\/+$/, "") || "/", query: new URLSearchParams(search) };
}

/** Update a single query parameter without adding a history entry. */
export function setQueryParam(key: string, value: string | null): void {
  const url = new URL(window.location.href);
  if (value) url.searchParams.set(key, value);
  else url.searchParams.delete(key);
  navigate(url.pathname + url.search, { replace: true });
}
