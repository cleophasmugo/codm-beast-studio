/** Optional access token, stored in localStorage. Every access is guarded: storage can throw
 * (private windows, blocked site data) and the app must keep working without it. */

const KEY = "beast.accessToken";
let memoryToken = "";

export function getToken(): string {
  try {
    const v = window.localStorage.getItem(KEY);
    if (v !== null) return v;
  } catch {
    /* storage unavailable: fall back to the in-memory copy */
  }
  return memoryToken;
}

export function setToken(token: string): void {
  memoryToken = token.trim();
  try {
    if (memoryToken) window.localStorage.setItem(KEY, memoryToken);
    else window.localStorage.removeItem(KEY);
  } catch {
    /* ignore */
  }
}

export function readPref<T>(key: string, fallback: T): T {
  try {
    const raw = window.localStorage.getItem(`beast.${key}`);
    return raw === null ? fallback : (JSON.parse(raw) as T);
  } catch {
    return fallback;
  }
}

export function writePref(key: string, value: unknown): void {
  try {
    window.localStorage.setItem(`beast.${key}`, JSON.stringify(value));
  } catch {
    /* ignore */
  }
}
