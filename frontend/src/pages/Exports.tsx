import { Film, ImageIcon, Play, Trash2 } from "lucide-react";
import { useMemo, useState } from "react";
import { api, mediaUrl, type ExportItem } from "../api";
import { DownloadLink, ExportPlayer } from "../components/ExportPlayer";
import { useToast } from "../components/Toast";
import { Badge, Button, ConfirmDialog, Empty, ErrorBanner, IconButton, Modal, PageHeader, Segmented, Spinner } from "../components/ui";
import { formatBytes, formatDate, formatDuration, formatLabel, formatResolution } from "../lib/format";
import { useAsync } from "../lib/hooks";
import { setQueryParam, useLocation } from "../lib/router";

type Filter = "all" | "video" | "preview" | "image";

export function Exports() {
  const toast = useToast();
  const { query } = useLocation();
  const exports = useAsync(() => api.listExports(), []);
  const [filter, setFilter] = useState<Filter>("all");
  const [deleting, setDeleting] = useState<ExportItem | null>(null);
  const [busy, setBusy] = useState(false);
  const playId = query.get("play");
  const playing = exports.data?.find((e) => e.id === playId) ?? null;

  const list = useMemo(() => (exports.data ?? []).filter((e) => filter === "all" || e.kind === filter), [exports.data, filter]);

  const remove = async () => {
    if (!deleting) return;
    setBusy(true);
    try {
      await api.deleteExport(deleting.id);
      exports.setData((l) => (l ?? []).filter((e) => e.id !== deleting.id));
      toast.success("Export deleted");
      setDeleting(null);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div>
      <PageHeader title="Export History" subtitle="Every rendered montage, preview and edited image. Play, download or clean up." />
      <div className="mb-5">
        <Segmented
          label="Show"
          value={filter}
          onChange={setFilter}
          options={[
            { value: "all", label: `All${exports.data ? ` (${exports.data.length})` : ""}` },
            { value: "video", label: "Montages" },
            { value: "preview", label: "Previews" },
            { value: "image", label: "Images" },
          ]}
        />
      </div>
      {exports.loading && !exports.data ? (
        <Spinner />
      ) : exports.error ? (
        <ErrorBanner onRetry={exports.reload}>{exports.error}</ErrorBanner>
      ) : !list.length ? (
        <Empty icon={<Film className="size-8" />} title="Nothing exported yet">
          Rendered montages and Image Studio exports appear here.
        </Empty>
      ) : (
        <ul className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {list.map((e) => (
            <li key={e.id} className="panel overflow-hidden" data-testid="export-card">
              <button type="button" className="group relative block aspect-video w-full bg-black" onClick={() => setQueryParam("play", e.id)} aria-label={`${e.kind === "image" ? "View" : "Play"} ${e.name}`}>
                {e.thumb_url ? (
                  <img src={mediaUrl(e.thumb_url)} alt="" className="size-full object-contain" loading="lazy" />
                ) : (
                  <div className="grid size-full place-items-center text-ink-500">{e.kind === "image" ? <ImageIcon className="size-8" /> : <Film className="size-8" />}</div>
                )}
                <span className="absolute inset-0 grid place-items-center bg-black/0 transition group-hover:bg-black/40">
                  <span className="grid size-12 place-items-center rounded-full bg-cyber/90 text-ink-950 opacity-0 shadow-[0_0_24px_#22d3ee] transition group-hover:opacity-100">
                    <Play className="size-5" aria-hidden />
                  </span>
                </span>
              </button>
              <div className="p-3.5">
                <div className="flex items-start gap-2">
                  <h2 className="min-w-0 flex-1 truncate text-sm font-bold text-white" title={e.name}>
                    {e.name}
                  </h2>
                  <IconButton label={`Delete ${e.name}`} onClick={() => setDeleting(e)} className="hover:text-rose-400">
                    <Trash2 className="size-4" />
                  </IconButton>
                </div>
                <div className="mt-1.5 flex flex-wrap gap-1.5">
                  <Badge tone={e.kind === "image" ? "violet" : e.kind === "preview" ? "amber" : "cyan"}>{e.kind === "video" ? "montage" : e.kind}</Badge>
                  <Badge>{formatLabel(e.format)}</Badge>
                  <Badge>{formatResolution(e.width, e.height)}</Badge>
                  {e.kind !== "image" && <Badge>{formatDuration(e.duration)}</Badge>}
                  <Badge>{formatBytes(e.size_bytes)}</Badge>
                </div>
                <div className="mt-3 flex items-center justify-between gap-2">
                  <span className="text-xs text-ink-400">{formatDate(e.created_at)}</span>
                  <DownloadLink item={e} size="sm" />
                </div>
              </div>
            </li>
          ))}
        </ul>
      )}

      <Modal open={!!playing} onClose={() => setQueryParam("play", null)} title={playing?.name ?? "Export"} wide>
        {playing && <ExportPlayer item={playing} />}
      </Modal>
      <ConfirmDialog
        open={!!deleting}
        title="Delete export?"
        message={<>Delete <strong className="text-white">{deleting?.name}</strong>? The file is removed from the server. The project itself is kept.</>}
        onConfirm={remove}
        onCancel={() => setDeleting(null)}
        busy={busy}
      />
      {exports.data && exports.data.length > 0 && (
        <div className="mt-6 text-right">
          <Button size="sm" variant="ghost" onClick={exports.reload}>
            Refresh
          </Button>
        </div>
      )}
    </div>
  );
}
