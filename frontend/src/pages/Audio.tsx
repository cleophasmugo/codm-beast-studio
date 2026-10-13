import { Music, SlidersHorizontal, Trash2 } from "lucide-react";
import { useCallback, useMemo, useState } from "react";
import { api, type GameAudio, type Media } from "../api";
import { AudioRow } from "../components/AudioRow";
import { OnlineMusicBrowser } from "../components/OnlineMusicBrowser";
import { ProjectSelect, useSelectedProjectId } from "../components/ProjectSelect";
import { SaveBar } from "../components/SaveBar";
import { useToast } from "../components/Toast";
import { UploadZone } from "../components/UploadZone";
import { Button, Card, CardTitle, ConfirmDialog, Empty, ErrorBanner, PageHeader, Segmented, SelectField, Slider, Spinner, Toggle } from "../components/ui";
import { useAsync } from "../lib/hooks";
import { useProjectSettings } from "../lib/useProjectSettings";

export function AudioPage() {
  const toast = useToast();
  const audio = useAsync(() => api.listMedia("audio"), []);
  const projectId = useSelectedProjectId();
  const ps = useProjectSettings(projectId);
  const [confirm, setConfirm] = useState<Media | null>(null);
  const [deleting, setDeleting] = useState(false);

  const tracks = audio.data ?? [];
  const library = useMemo(() => tracks.filter((t) => t.source === "library"), [tracks]);
  const uploads = useMemo(() => tracks.filter((t) => t.source !== "library"), [tracks]);

  const onUploaded = useCallback(
    (items: Media[]) => {
      const a = items.filter((m) => m.kind === "audio");
      audio.setData((prev) => [...a, ...(prev ?? [])]);
      toast.success(`${a.length} track${a.length === 1 ? "" : "s"} uploaded`);
    },
    [audio, toast],
  );

  const onImported = useCallback(
    (m: Media) => audio.setData((prev) => [m, ...(prev ?? []).filter((x) => x.id !== m.id)]),
    [audio],
  );

  const del = async () => {
    if (!confirm) return;
    setDeleting(true);
    try {
      await api.deleteMedia(confirm.id);
      audio.setData((prev) => (prev ?? []).filter((m) => m.id !== confirm.id));
      toast.success("Track deleted");
      setConfirm(null);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : String(e));
    } finally {
      setDeleting(false);
    }
  };

  const s = ps.settings;
  return (
    <div className="space-y-6">
      <PageHeader title="Music and Audio" subtitle="Preview the royalty-free library, upload your own tracks and mix each project's sound." />
      <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_400px]">
        <div className="min-w-0 space-y-6">
          <Card>
            <CardTitle icon={<Music className="size-4" />}>Library tracks</CardTitle>
            {audio.loading && !audio.data ? (
              <Spinner />
            ) : audio.error ? (
              <ErrorBanner onRetry={audio.reload}>{audio.error}</ErrorBanner>
            ) : library.length ? (
              <div className="space-y-3">
                {library.map((m) => (
                  <AudioRow key={m.id} media={m} />
                ))}
              </div>
            ) : (
              <p className="text-sm text-ink-400">No library tracks installed.</p>
            )}
          </Card>
          <Card>
            <CardTitle icon={<Music className="size-4" />}>Your music</CardTitle>
            {uploads.length ? (
              <div className="space-y-3">
                {uploads.map((m) => (
                  <AudioRow
                    key={m.id}
                    media={m}
                    actions={
                      <Button size="sm" variant="ghost" aria-label={`Delete ${m.name}`} onClick={() => setConfirm(m)} icon={<Trash2 className="size-3.5" />} />
                    }
                  />
                ))}
              </div>
            ) : (
              <Empty title="No music yet">Add a track from the online browser or upload one below. Only use music you have the rights to.</Empty>
            )}
            <div className="mt-4">
              <UploadZone compact accept=".mp3,.wav,.m4a,.aac,.ogg,.flac,audio/*" title="Upload music" hint="MP3, WAV, M4A, AAC, OGG or FLAC." onUploaded={onUploaded} />
            </div>
          </Card>
          <OnlineMusicBrowser onImported={onImported} />
        </div>

        <div className="min-w-0">
          <Card className="xl:sticky xl:top-6">
            <CardTitle icon={<SlidersHorizontal className="size-4" />}>Project audio mix</CardTitle>
            <ProjectSelect />
            {projectId && ps.loading && !s && <Spinner />}
            {ps.error && (
              <div className="mt-3">
                <ErrorBanner onRetry={ps.reload}>{ps.error}</ErrorBanner>
              </div>
            )}
            {s && (
              <div className="mt-4 space-y-4">
                <SelectField
                  label="Music track"
                  value={s.music_id ?? ""}
                  onChange={(e) => ps.update((x) => ({ ...x, music_id: e.target.value || null }))}
                >
                  <option value="">No music</option>
                  {tracks.map((t) => (
                    <option key={t.id} value={t.id}>
                      {t.name}
                      {t.source === "library" ? " (library)" : ""}
                    </option>
                  ))}
                </SelectField>
                <Slider label="Music volume" value={s.music_volume} min={0} max={2} format={(v) => `${Math.round(v * 100)}%`} onChange={(v) => ps.update((x) => ({ ...x, music_volume: v }))} />
                <Segmented<GameAudio>
                  label="Game audio"
                  value={s.game_audio}
                  onChange={(v) => ps.update((x) => ({ ...x, game_audio: v }))}
                  options={[
                    { value: "keep", label: "Keep" },
                    { value: "reduce", label: "Reduce" },
                    { value: "mute", label: "Mute" },
                  ]}
                />
                <div className="rounded-xl border border-white/[0.08] p-3">
                  <Toggle label="Ducking" description="Lower the music when the game gets loud" checked={s.ducking} onChange={(v) => ps.update((x) => ({ ...x, ducking: v }))} />
                  <Slider label="Duck amount" value={s.duck_amount} min={0} max={1} disabled={!s.ducking} format={(v) => `${Math.round(v * 100)}%`} onChange={(v) => ps.update((x) => ({ ...x, duck_amount: v }))} />
                </div>
                <Toggle label="Normalize loudness" description="Even out the final mix for social platforms" checked={s.normalize_audio} onChange={(v) => ps.update((x) => ({ ...x, normalize_audio: v }))} />
                <Toggle label="Transition sound effects" description="Whooshes and hits on flash, zoom and whip transitions" checked={s.transition_sfx} onChange={(v) => ps.update((x) => ({ ...x, transition_sfx: v }))} />
                <p className="text-xs text-ink-400">Changes apply on the next render of this project (Projects → Render, or Re-run Auto Edit).</p>
              </div>
            )}
          </Card>
        </div>
      </div>
      <SaveBar dirty={ps.dirty} saving={ps.saving} onSave={async () => (await ps.save()) && toast.success("Audio settings saved")} onDiscard={ps.reload} />
      <ConfirmDialog
        open={!!confirm}
        title="Delete track?"
        message={<>Delete <strong>{confirm?.name}</strong>? Projects using it will render without music.</>}
        onConfirm={del}
        onCancel={() => setConfirm(null)}
        busy={deleting}
      />
    </div>
  );
}
