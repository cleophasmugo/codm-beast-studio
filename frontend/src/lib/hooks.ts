import { useCallback, useEffect, useRef, useState } from "react";
import { api, isActive, type Job } from "../api";

export interface AsyncState<T> {
  data: T | undefined;
  error: string | null;
  loading: boolean;
  reload: () => void;
  setData: (v: T | ((prev: T | undefined) => T)) => void;
}

/** Load data on mount / when deps change. Errors become readable strings. */
export function useAsync<T>(fn: () => Promise<T>, deps: unknown[]): AsyncState<T> {
  const [data, setDataState] = useState<T | undefined>(undefined);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [tick, setTick] = useState(0);
  const fnRef = useRef(fn);
  fnRef.current = fn;

  useEffect(() => {
    let alive = true;
    setLoading(true);
    fnRef
      .current()
      .then((d) => {
        if (!alive) return;
        setDataState(d);
        setError(null);
      })
      .catch((e: unknown) => {
        if (alive) setError(e instanceof Error ? e.message : String(e));
      })
      .finally(() => alive && setLoading(false));
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, tick]);

  const reload = useCallback(() => setTick((t) => t + 1), []);
  const setData = useCallback((v: T | ((prev: T | undefined) => T)) => {
    setDataState((prev) => (typeof v === "function" ? (v as (p: T | undefined) => T)(prev) : v));
  }, []);
  return { data, error, loading, reload, setData };
}

/** Poll a job about once a second until it finishes. */
export function useJob(jobId: string | null, onFinish?: (job: Job) => void, intervalMs = 1000) {
  const [job, setJob] = useState<Job | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [generation, setGeneration] = useState(0);
  const finishRef = useRef(onFinish);
  finishRef.current = onFinish;

  useEffect(() => {
    if (!jobId) {
      setJob(null);
      return;
    }
    let alive = true;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let failures = 0;
    const tick = async () => {
      try {
        const j = await api.getJob(jobId);
        if (!alive) return;
        failures = 0;
        setError(null);
        setJob(j);
        if (!isActive(j)) {
          finishRef.current?.(j);
          return;
        }
      } catch (e) {
        if (!alive) return;
        failures++;
        // the backend may restart briefly; keep trying but say so
        if (failures > 2) setError(e instanceof Error ? e.message : String(e));
      }
      timer = setTimeout(tick, intervalMs);
    };
    void tick();
    return () => {
      alive = false;
      if (timer) clearTimeout(timer);
    };
  }, [jobId, intervalMs, generation]);

  /** Restart polling after a retry (the job keeps its id). */
  const restart = useCallback((j?: Job) => {
    if (j) setJob(j);
    setGeneration((g) => g + 1);
  }, []);
  return { job, error, restart };
}

export function useDebounced<T>(value: T, ms: number): T {
  const [v, setV] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setV(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return v;
}

export function useInterval(cb: () => void, ms: number | null): void {
  const ref = useRef(cb);
  ref.current = cb;
  useEffect(() => {
    if (ms === null) return;
    const t = setInterval(() => ref.current(), ms);
    return () => clearInterval(t);
  }, [ms]);
}

export function errorText(e: unknown): string {
  return e instanceof Error ? e.message : String(e);
}
