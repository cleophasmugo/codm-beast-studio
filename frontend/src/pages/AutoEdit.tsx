import { Clapperboard, Film, Music2, Type, Volume2, Wand2 } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, ASPECTS, type Aspect, type GameAudio, type Job, type Media, type PresetName } from "../api";
import { AudioRow } from "../components/AudioRow";
import { DurationPicker, durationToSeconds, secondsToDuration, type DurationChoice } from "../components/DurationPicker";
import { JobProgressCard } from "../components/JobProgressCard";
import { JobResult } from "../components/JobResult";
import { MediaPicker } from "../components/MediaPicker";
import { PresetPicker } from "../components/PresetPicker";
import { useToast } from "../components/Toast";
import { UploadZone } from "../components/UploadZone";
import { Button, Card, CardTitle, ErrorBanner, Note, PageHeader, Segmented, Spinner, TextField, cx } from "../components/ui";
import { titleCase } from "../lib/format";
import { useAsync } from "../lib/hooks";

export function AutoEdit() {
  const toast = useToast();
  const presets = useAsync(() => api.presets(), []);
  const media = useAsync(() => api.listMedia(), []);

  const [selected, setSelected] = useState<string[]>([]);
  const [preset, setPreset] = useState<PresetName>("beast");
  const [duration, setDuration] = useState<DurationChoice>("30");
  const [aspect, setAspect] = useState<Aspect>("16:9");
  const [musicId, setMusicId] = useState<string | null>(null);
  const [gameAudio, setGameAudio] = useState<GameAudio>("reduce");
  const [name, setName] = useState("");
  const [title, setTitle] = useState("");
  const [subtitle, setSubtitle] = useState("");
  const [outro, setOutro] = useState("");
  const [jobId, setJobId] = useState<string | null>(null);
  const [done, setDone] = useState<Job | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [jobActive, setJobActive] = useState(false);
  const resultRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (jobId) resultRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [jobId]);

  const footage = useMemo(() => (media.data ?? []).filter((m) => m.kind === "video" || m.kind === "image"), [media.data]);
  const audio = useMemo(() => (media.data ?? []).filter((m) => m.kind === "audio"), [media.data]);

  const choosePreset = (id: PresetName) => {
    setPreset(id);
    const p = presets.data?.find((x) => x.id === id);
    if (p) {
      setAspect(p.aspect);
      setDuration(secondsToDuration(p.target_duration));
    }
  };

  const onUploaded = useCallback(
    (items: Media[]) => {
      media.setData((prev) => [...items, ...(prev ?? [])]);
      const vis = items.filter((m) => m.kind === "video" || m.kind === "image").map((m) => m.id);
      if (vis.length) setSelected((s) => [...new Set([...s, ...vis])]);
      const song = items.find((m) => m.kind === "audio");
      if (song) setMusicId(song.id);
      toast.success(`${items.length} file${items.length === 1 ? "" : "s"} uploaded`);
    },
    [media, toast],
  );

  const run = async () => {
    setBusy(true);
    setError(null);
    setDone(null);
    try {
      const label = presets.data?.find((p) => p.id === preset)?.label ?? titleCase(preset);
      const project = await api.createProject({ name: name.trim() || `${label} montage`, media_ids: selected });
      const styled = await api.applyPreset(project.id, preset);
      const settings = {
        ...styled.settings,
        target_duration: durationToSeconds(duration),
        aspect,
        music_id: musicId,
        game_audio: gameAudio,
        title: title.trim(),
        subtitle: subtitle.trim(),
        outro_text: outro.trim(),
      };
      const job = await api.autoEdit(project.id, settings, true);
      setJobId(job.id);
      setJobActive(true);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const toggle = (id: string) => setSelected((s) => (s.includes(id) ? s.filter((x) => x !== id) : [...s, id]));

  return (
    <div className="space-y-6">
      <PageHeader
        title="Auto Edit"
        subtitle="Choose footage and a style. Beast Studio analyses motion, sound and flashes, cuts to the music and renders the result."
      />

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_380px]">
        <div className="min-w-0 space-y-6">
          <Card>
            <CardTitle icon={<Film className="size-4" />} action={<span className="text-xs text-ink-400">{selected.length} selected</span>}>
              Footage
            </CardTitle>
            {media.loading && !media.data ? (
              <Spinner />
            ) : media.error ? (
              <ErrorBanner onRetry={media.reload}>{media.error}</ErrorBanner>
            ) : (
              <MediaPicker media={footage} selected={selected} onToggle={toggle} />
            )}
            <div className="mt-4">
              <UploadZone compact onUploaded={onUploaded} title="Add more clips, screenshots or music" hint="Uploads are added to the selection." />
            </div>
          </Card>

          <Card>
            <CardTitle icon={<Wand2 className="size-4" />}>Style preset</CardTitle>
            {presets.data ? (
              <PresetPicker presets={presets.data} value={preset} onChange={choosePreset} />
            ) : presets.error ? (
              <ErrorBanner onRetry={presets.reload}>{presets.error}</ErrorBanner>
            ) : (
              <Spinner />
            )}
            <div className="mt-5 grid gap-5 sm:grid-cols-2">
              <DurationPicker value={duration} onChange={setDuration} />
              <Segmented label="Aspect ratio" value={aspect} onChange={setAspect} options={ASPECTS.map((a) => ({ value: a, label: a }))} />
            </div>
          </Card>

          <Card>
            <CardTitle icon={<Music2 className="size-4" />}>Music</CardTitle>
            <div className="space-y-2.5">
              <label
                className={cx(
                  "flex cursor-pointer items-center gap-2 rounded-xl border p-3 text-sm",
                  musicId === null ? "border-toxic/60 bg-toxic/[0.06]" : "border-white/[0.08] bg-ink-900/60",
                )}
              >
                <input type="radio" name="music-track" checked={musicId === null} onChange={() => setMusicId(null)} className="size-4 accent-[#a3e635]" />
                <span className="font-semibold text-white">No music</span>
                <span className="text-ink-400">(game audio only; cuts follow the action instead of a beat)</span>
              </label>
              {audio.map((a) => (
                <AudioRow key={a.id} media={a} selected={musicId === a.id} onSelect={() => setMusicId(a.id)} />
              ))}
            </div>
            <div className="mt-4">
              <UploadZone
                compact
                accept=".mp3,.wav,.m4a,.aac,.ogg,.flac,audio/*"
                title="Upload your own music"
                hint="MP3, WAV, M4A, AAC, OGG or FLAC. Only use music you have the rights to."
                onUploaded={onUploaded}
              />
            </div>
          </Card>
        </div>

        <div className="min-w-0 space-y-6">
          <Card>
            <CardTitle icon={<Volume2 className="size-4" />}>Game audio</CardTitle>
            <Segmented
              label="Gameplay sound"
              value={gameAudio}
              onChange={setGameAudio}
              options={[
                { value: "keep", label: "Keep" },
                { value: "reduce", label: "Reduce" },
                { value: "mute", label: "Mute" },
              ]}
            />
            <p className="mt-2 text-xs text-ink-400">Reduce lowers gunfire under the music; ducking and volume are in Music and Audio.</p>
          </Card>

          <Card>
            <CardTitle icon={<Type className="size-4" />}>Titles</CardTitle>
            <div className="space-y-3">
              <TextField label="Project name" value={name} onChange={setName} placeholder="My Montage" maxLength={200} />
              <TextField label="Title card" value={title} onChange={setTitle} placeholder="e.g. RANKED CLUTCHES" maxLength={80} />
              <TextField label="Subtitle" value={subtitle} onChange={setSubtitle} placeholder="e.g. Season 9 · Legendary" maxLength={120} />
              <TextField label="Outro text" value={outro} onChange={setOutro} placeholder="e.g. Follow for more" maxLength={80} />
            </div>
          </Card>

          <Card glow className="xl:sticky xl:top-6">
            <Button
              variant="primary"
              size="lg"
              className="w-full"
              onClick={run}
              loading={busy}
              disabled={!selected.length || jobActive}
              icon={<Clapperboard className="size-5" />}
              data-testid="run-auto-edit"
            >
              Auto Edit My Video
            </Button>
            {!selected.length && <p className="mt-2 text-center text-xs text-ink-400">Select at least one clip or screenshot.</p>}
            <div className="mt-3">
              <Note>Highlights are chosen from motion, sound spikes and flashes. They are a starting point, not a guarantee of kills.</Note>
            </div>
            {error && (
              <div className="mt-3">
                <ErrorBanner>{error}</ErrorBanner>
              </div>
            )}
          </Card>
        </div>
      </div>

      {jobId && (
        <div ref={resultRef} className="scroll-mt-20">
        <Card glow>
          <CardTitle icon={<Clapperboard className="size-4" />}>Your montage</CardTitle>
          <div className="space-y-4">
            <JobProgressCard
              key={jobId}
              jobId={jobId}
              title="Auto Edit"
              onFinish={(j) => {
                setJobActive(false);
                if (j.status === "done") {
                  setDone(j);
                  toast.success("Your montage is ready");
                } else {
                  setDone(null);
                }
              }}
            />
            {done && done.id === jobId && <JobResult job={done} />}
          </div>
        </Card>
        </div>
      )}
    </div>
  );
}
