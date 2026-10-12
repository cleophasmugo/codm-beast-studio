import { useCallback, useEffect, useState } from "react";
import { api, type Project, type ProjectSettings } from "../api";

/** Load a project's settings, edit them locally, PATCH them back on save. */
export function useProjectSettings(projectId: string | null) {
  const [project, setProject] = useState<Project | null>(null);
  const [settings, setSettings] = useState<ProjectSettings | null>(null);
  const [dirty, setDirty] = useState(false);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [tick, setTick] = useState(0);

  useEffect(() => {
    if (!projectId) return;
    let alive = true;
    setLoading(true);
    api
      .getProject(projectId)
      .then((p) => {
        if (!alive) return;
        setProject(p);
        setSettings(p.settings);
        setDirty(false);
        setError(null);
      })
      .catch((e: unknown) => alive && setError(e instanceof Error ? e.message : String(e)))
      .finally(() => alive && setLoading(false));
    return () => {
      alive = false;
    };
  }, [projectId, tick]);

  const update = useCallback((fn: (s: ProjectSettings) => ProjectSettings) => {
    setSettings((s) => (s ? fn(s) : s));
    setDirty(true);
  }, []);

  const save = useCallback(async (): Promise<Project | null> => {
    if (!projectId || !settings) return null;
    setSaving(true);
    setError(null);
    try {
      const p = await api.updateProject(projectId, { settings });
      setProject(p);
      setSettings(p.settings);
      setDirty(false);
      return p;
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      return null;
    } finally {
      setSaving(false);
    }
  }, [projectId, settings]);

  const reload = useCallback(() => setTick((t) => t + 1), []);
  return { project, settings, update, save, dirty, loading, saving, error, reload };
}
