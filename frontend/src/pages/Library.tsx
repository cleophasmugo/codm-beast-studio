import { Folder, LayoutGrid, Library as LibraryIcon, Pencil, Trash2 } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { api, mediaUrl, type Media, type MediaKind } from "../api";
import { MediaThumb } from "../components/MediaThumb";
import { useToast } from "../components/Toast";
import { UploadZone } from "../components/UploadZone";
import { Badge, Button, ConfirmDialog, Empty, ErrorBanner, Modal, PageHeader, Segmented, SelectField, Spinner, TextField } from "../components/ui";
import { formatBytes, formatDate, formatDuration, formatResolution } from "../lib/format";
import { useAsync } from "../lib/hooks";

type KindFilter = "all" | MediaKind;

function infoRows(m: Media): [string, string][] {
  const i = m.info;
  const rows: [string, string][] = [];
  if (i.duration) rows.push(["Duration", formatDuration(i.duration)]);
  if (i.width && i.height) rows.push(["Resolution", formatResolution(i.width, i.height)]);
  if (i.fps) rows.push(["Frame rate", `${Number(i.fps).toFixed(2).replace(/\.00$/, "")} fps`]);
  if (i.video_codec) rows.push(["Video codec", String(i.video_codec)]);
  if (m.kind === "video" || m.kind === "audio")
    rows.push(["Audio", i.has_audio === false ? "None" : [i.audio_codec, i.sample_rate ? `${i.sample_rate} Hz` : "", i.channels ? `${i.channels} ch` : ""].filter(Boolean).join(" · ") || "Yes"]);
  if (i.bitrate) rows.push(["Bitrate", `${Math.round(Number(i.bitrate) / 1000)} kbps`]);
  if (m.kind === "image" || m.kind === "sticker") rows.push(["Transparency", i.has_alpha ? "Yes" : "No"]);
  rows.push(["Size", formatBytes(m.size_bytes)]);
  rows.push(["Type", m.mime]);
  rows.push(["Original file", m.original_filename]);
  rows.push(["Added", formatDate(m.created_at)]);
  return rows;
}

export function Library() {
  const toast = useToast();
  const media = useAsync(() => api.listMedia(), []);
  const [kind, setKind] = useState<KindFilter>("all");
  const [folder, setFolder] = useState<string>("__all");
  const [open, setOpen] = useState<Media | null>(null);
  const [confirm, setConfirm] = useState<Media | null>(null);
  const [busy, setBusy] = useState(false);

  const folders = useMemo(() => [...new Set((media.data ?? []).map((m) => m.folder).filter(Boolean))].sort(), [media.data]);
  const list = useMemo(
    () => (media.data ?? []).filter((m) => (kind === "all" || m.kind === kind) && (folder === "__all" || m.folder === folder)),
    [media.data, kind, folder],
  );

  const onUploaded = useCallback(
    (items: Media[]) => {
      media.setData((prev) => [...items, ...(prev ?? [])]);
      toast.success(`${items.length} file${items.length === 1 ? "" : "s"} uploaded`);
    },
    [media, toast],
  );

  const replace = (m: Media) => {
    media.setData((l) => (l ?? []).map((x) => (x.id === m.id ? m : x)));
    setOpen(m);
  };

  const remove = async () => {
    if (!confirm) return;
    setBusy(true);
    try {
      await api.deleteMedia(confirm.id);
      media.setData((l) => (l ?? []).filter((x) => x.id !== confirm.id));
      setConfirm(null);
      setOpen(null);
      toast.success("Deleted");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-6">
      <PageHeader title="Media Library" subtitle="Everything you've uploaded plus the built-in royalty-free music and stickers." />
      <UploadZone compact onUploaded={onUploaded} folder={folder !== "__all" ? folder : ""} />
      <div className="flex flex-col gap-4 sm:flex-row sm:items-end">
        <Segmented
          label="Kind"
          value={kind}
          onChange={setKind}
          options={[
            { value: "all", label: "All" },
            { value: "video", label: "Videos" },
            { value: "image", label: "Screenshots" },
            { value: "audio", label: "Audio" },
            { value: "sticker", label: "Stickers" },
          ]}
        />
        {folders.length > 0 && (
          <SelectField label="Folder" value={folder} onChange={(e) => setFolder(e.target.value)} className="sm:w-48">
            <option value="__all">All folders</option>
            <option value="">(No folder)</option>
            {folders.map((f) => (
              <option key={f} value={f}>
                {f}
              </option>
            ))}
          </SelectField>
        )}
      </div>
      {media.loading && !media.data ? (
        <Spinner />
      ) : media.error ? (
        <ErrorBanner onRetry={media.reload}>{media.error}</ErrorBanner>
      ) : !list.length ? (
        <Empty icon={<LibraryIcon className="size-8" />} title="Nothing here">
          Upload files above or change the filter.
        </Empty>
      ) : (
        <ul className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5">
          {list.map((m) => (
            <li key={m.id}>
              <button type="button" onClick={() => setOpen(m)} className="block w-full rounded-xl border border-white/[0.08] bg-ink-900/60 p-1.5 text-left transition hover:border-cyber/40" data-testid="library-item">
                <MediaThumb media={m} />
                <div className="mt-1.5 px-0.5">
                  <div className="truncate text-xs font-semibold text-white">{m.name}</div>
                  <div className="flex items-center gap-1 truncate text-[11px] text-ink-400">
                    {m.folder && (
                      <>
                        <Folder className="size-3" aria-hidden /> {m.folder} ·
                      </>
                    )}
                    {m.source === "library" ? "Library" : formatBytes(m.size_bytes)}
                  </div>
                </div>
              </button>
            </li>
          ))}
        </ul>
      )}

      <MediaDetails media={open} onClose={() => setOpen(null)} onChanged={replace} onDelete={(m) => setConfirm(m)} folders={folders} />
      <ConfirmDialog
        open={!!confirm}
        title="Delete file?"
        message={<>Delete <strong className="text-white">{confirm?.name}</strong>? It's removed from any project that uses it.</>}
        onConfirm={remove}
        onCancel={() => setConfirm(null)}
        busy={busy}
      />
    </div>
  );
}

function MediaDetails({
  media,
  onClose,
  onChanged,
  onDelete,
  folders,
}: {
  media: Media | null;
  onClose: () => void;
  onChanged: (m: Media) => void;
  onDelete: (m: Media) => void;
  folders: string[];
}) {
  const toast = useToast();
  const [name, setName] = useState("");
  const [folder, setFolder] = useState("");
  const [sheet, setSheet] = useState(false);
  const [saving, setSaving] = useState(false);
  useEffect(() => {
    setName(media?.name ?? "");
    setFolder(media?.folder ?? "");
    setSheet(false);
  }, [media]);
  if (!media) return <Modal open={false} onClose={onClose} title="">{null}</Modal>;
  const isLib = media.source === "library";

  const save = async () => {
    setSaving(true);
    try {
      onChanged(await api.updateMedia(media.id, { name: name.trim(), folder: folder.trim() }));
      toast.success("Saved");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal open onClose={onClose} title={media.name} wide>
      <div className="grid gap-5 md:grid-cols-[minmax(0,1fr)_280px]">
        <div className="min-w-0 space-y-3">
          <div className={`overflow-hidden rounded-xl border border-white/10 ${media.kind === "sticker" ? "checker" : "bg-black"}`}>
            {media.kind === "video" ? (
              sheet && media.contact_sheet_url ? (
                <img src={mediaUrl(media.contact_sheet_url)} alt={`Contact sheet of ${media.name}`} className="w-full" />
              ) : (
                <video src={mediaUrl(media.url)} poster={media.thumb_url ? mediaUrl(media.thumb_url) : undefined} controls playsInline preload="metadata" className="aspect-video w-full" />
              )
            ) : media.kind === "audio" ? (
              <div className="p-4">
                {media.thumb_url && <img src={mediaUrl(media.thumb_url)} alt="Waveform" className="mb-3 h-20 w-full object-fill" />}
                <audio src={mediaUrl(media.url)} controls className="w-full" />
              </div>
            ) : (
              <img src={mediaUrl(media.url)} alt={media.name} className="mx-auto max-h-[55vh] w-auto object-contain" />
            )}
          </div>
          {media.kind === "video" && media.contact_sheet_url && (
            <Button size="sm" variant="secondary" icon={<LayoutGrid className="size-3.5" />} onClick={() => setSheet((v) => !v)}>
              {sheet ? "Show video" : "Contact sheet"}
            </Button>
          )}
          {media.license && <p className="text-xs text-ink-400">License: {media.license}</p>}
        </div>
        <div className="space-y-4">
          <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-3 gap-y-1.5 text-xs">
            {infoRows(media).map(([k, v]) => (
              <div key={k} className="contents">
                <dt className="text-ink-400">{k}</dt>
                <dd className="truncate text-ink-100" title={v}>
                  {v}
                </dd>
              </div>
            ))}
          </dl>
          {media.has_analysis && <Badge tone="green">Analysed</Badge>}
          {isLib ? (
            <p className="text-xs text-ink-400">Built-in library item (read-only).</p>
          ) : (
            <form
              className="space-y-3 border-t border-white/5 pt-4"
              onSubmit={(e) => {
                e.preventDefault();
                void save();
              }}
            >
              <TextField label="Name" value={name} onChange={setName} maxLength={200} />
              <TextField label="Folder" value={folder} onChange={setFolder} maxLength={100} placeholder="e.g. Ranked" hint={folders.length ? `Existing: ${folders.join(", ")}` : undefined} />
              <div className="flex gap-2">
                <Button type="submit" variant="primary" size="sm" loading={saving} disabled={!name.trim()} icon={<Pencil className="size-3.5" />}>
                  Save
                </Button>
                <Button variant="danger" size="sm" onClick={() => onDelete(media)} icon={<Trash2 className="size-3.5" />}>
                  Delete
                </Button>
              </div>
            </form>
          )}
        </div>
      </div>
    </Modal>
  );
}
