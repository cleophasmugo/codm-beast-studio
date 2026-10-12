import { Brush, Cpu, KeyRound, Lock, ShieldCheck } from "lucide-react";
import { useState } from "react";
import { api } from "../api";
import { useToast } from "../components/Toast";
import { Badge, Button, Card, CardTitle, ErrorBanner, Note, PageHeader, Spinner, Stat } from "../components/ui";
import { formatBytes, formatLabel, titleCase } from "../lib/format";
import { useAsync } from "../lib/hooks";
import { getToken, setToken } from "../lib/token";

export function SettingsPage() {
  const toast = useToast();
  const system = useAsync(() => api.system(), []);
  const [token, setTokenState] = useState(getToken());
  const [show, setShow] = useState(false);
  const [cleaning, setCleaning] = useState(false);
  const [cleanup, setCleanup] = useState<Record<string, unknown> | null>(null);

  const saveToken = () => {
    setToken(token);
    toast.success(token.trim() ? "Access token saved" : "Access token cleared");
    system.reload();
  };

  const runCleanup = async () => {
    setCleaning(true);
    try {
      const r = await api.cleanup();
      setCleanup(r);
      toast.success("Cleanup finished");
      system.reload();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : String(e));
    } finally {
      setCleaning(false);
    }
  };

  const s = system.data;
  return (
    <div className="space-y-6">
      <PageHeader title="Settings" subtitle="Server access, capabilities and storage housekeeping." />
      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardTitle icon={<KeyRound className="size-4" />}>Access token</CardTitle>
          <p className="mb-3 text-sm text-ink-300">
            If the server sets <code className="rounded bg-ink-950 px-1 font-mono text-xs text-cyan-200">BEAST_API_TOKEN</code>, enter it here. It's kept in this
            browser only and sent with every request.
          </p>
          <form
            className="space-y-3"
            onSubmit={(e) => {
              e.preventDefault();
              saveToken();
            }}
          >
            <label htmlFor="token" className="label">
              Token
            </label>
            <div className="flex gap-2">
              <input
                id="token"
                type={show ? "text" : "password"}
                autoComplete="off"
                className="field font-mono"
                value={token}
                onChange={(e) => setTokenState(e.target.value)}
                placeholder="Leave empty when the server has no token"
              />
              <Button variant="ghost" onClick={() => setShow((v) => !v)} aria-pressed={show}>
                {show ? "Hide" : "Show"}
              </Button>
            </div>
            <div className="flex gap-2">
              <Button type="submit" variant="primary" icon={<Lock className="size-4" />}>
                Save token
              </Button>
              {token && (
                <Button
                  variant="ghost"
                  onClick={() => {
                    setTokenState("");
                    setToken("");
                    toast.success("Access token cleared");
                    system.reload();
                  }}
                >
                  Clear
                </Button>
              )}
            </div>
          </form>
          {s && (
            <p className="mt-3 text-xs text-ink-400">
              This server {s.auth_required ? <Badge tone="amber">requires a token</Badge> : <Badge tone="green">does not require a token</Badge>}
            </p>
          )}
        </Card>

        <Card>
          <CardTitle icon={<ShieldCheck className="size-4" />}>Privacy</CardTitle>
          <div className="space-y-2 text-sm text-ink-300">
            <p>
              Uploads may contain personal information, such as your player name, UID, friends' names, chat messages or voice in the game audio.
            </p>
            <p>
              Everything you upload and export is stored on this server until you delete it
              {s && s.limits.retention_days > 0 ? ` or it expires after ${s.limits.retention_days} days` : ""}. Nothing is sent to third-party services.
            </p>
            <p>Delete files from the Media Library and Export History when you no longer need them.</p>
          </div>
        </Card>
      </div>

      <Card>
        <CardTitle icon={<Cpu className="size-4" />}>Server</CardTitle>
        {system.loading && !s ? (
          <Spinner />
        ) : system.error ? (
          <ErrorBanner onRetry={system.reload}>{system.error}</ErrorBanner>
        ) : s ? (
          <div className="space-y-5">
            <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
              <Stat label="App version" value={s.version} />
              <Stat label="Job backend" value={titleCase(s.job_backend)} hint={s.job_backend === "thread" ? "In-process worker" : "Celery workers"} />
              <Stat label="Storage used" value={formatBytes(s.storage.total_bytes)} hint={`Work files ${formatBytes(s.storage.work_bytes)}`} />
              <Stat label="Retention" value={s.limits.retention_days > 0 ? `${s.limits.retention_days} days` : "Keep forever"} />
            </div>
            <div>
              <p className="label">FFmpeg</p>
              <code className="block rounded-lg bg-ink-950 p-2.5 font-mono text-xs break-all text-cyan-200">{s.ffmpeg}</code>
            </div>
            <div>
              <p className="label">Export formats</p>
              <div className="flex flex-wrap gap-2">
                {Object.entries(s.formats).map(([f, ok]) => (
                  <Badge key={f} tone={ok ? "green" : "red"}>
                    {formatLabel(f)}: {ok ? "available" : "unavailable"}
                  </Badge>
                ))}
              </div>
            </div>
            <div>
              <p className="label">Limits</p>
              <ul className="grid gap-1 text-sm text-ink-200 sm:grid-cols-3">
                <li>Upload: {s.limits.max_upload_mb} MB per file</li>
                <li>Video: {s.limits.max_video_minutes} min</li>
                <li>Audio: {s.limits.max_audio_minutes} min</li>
              </ul>
            </div>
            <div>
              <p className="label">Highlight detectors</p>
              <div className="flex flex-wrap gap-1.5">
                {s.detectors.length ? s.detectors.map((d) => <Badge key={d}>{d}</Badge>) : <span className="text-sm text-ink-400">Built-in heuristics only</span>}
              </div>
            </div>
          </div>
        ) : null}
      </Card>

      <Card>
        <CardTitle icon={<Brush className="size-4" />}>Cleanup</CardTitle>
        <p className="mb-3 text-sm text-ink-300">
          Removes stale temporary work folders and, if a retention period is set, uploads and exports older than it. Library music and stickers are
          never removed.
        </p>
        <Button variant="secondary" onClick={runCleanup} loading={cleaning}>
          Run cleanup now
        </Button>
        {cleanup && (
          <div className="mt-3">
            <Note>
              Removed{" "}
              {Object.entries(cleanup)
                .map(([k, v]) => `${String(v)} ${titleCase(k).toLowerCase()}`)
                .join(", ")}
              .
            </Note>
          </div>
        )}
      </Card>
    </div>
  );
}
