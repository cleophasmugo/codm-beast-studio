import { motion } from "framer-motion";
import { Clapperboard, FolderOpen, Pencil, Plus, Trash2 } from "lucide-react";
import { useState } from "react";
import { api, mediaUrl, timelineDuration, type Project } from "../api";
import { presetIcon } from "../components/PresetPicker";
import { useToast } from "../components/Toast";
import { Badge, Button, ConfirmDialog, Empty, ErrorBanner, IconButton, Modal, PageHeader, Spinner, TextField } from "../components/ui";
import { formatDuration, timeAgo, titleCase } from "../lib/format";
import { useAsync } from "../lib/hooks";
import { navigate } from "../lib/router";

export function Projects() {
  const toast = useToast();
  const projects = useAsync(() => api.listProjects(), []);
  const [renaming, setRenaming] = useState<Project | null>(null);
  const [newName, setNewName] = useState("");
  const [deleting, setDeleting] = useState<Project | null>(null);
  const [busy, setBusy] = useState(false);

  const rename = async () => {
    if (!renaming || !newName.trim()) return;
    setBusy(true);
    try {
      const p = await api.updateProject(renaming.id, { name: newName.trim() });
      projects.setData((l) => (l ?? []).map((x) => (x.id === p.id ? p : x)));
      setRenaming(null);
      toast.success("Project renamed");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const remove = async () => {
    if (!deleting) return;
    setBusy(true);
    try {
      await api.deleteProject(deleting.id);
      projects.setData((l) => (l ?? []).filter((x) => x.id !== deleting.id));
      setDeleting(null);
      toast.success("Project deleted");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div>
      <PageHeader
        title="My Projects"
        subtitle="Open a project to trim clips, reorder, add text, change music and re-render."
        actions={
          <Button variant="primary" icon={<Plus className="size-4" />} onClick={() => navigate("/auto-edit")}>
            New montage
          </Button>
        }
      />
      {projects.loading && !projects.data ? (
        <Spinner />
      ) : projects.error ? (
        <ErrorBanner onRetry={projects.reload}>{projects.error}</ErrorBanner>
      ) : !projects.data?.length ? (
        <Empty icon={<Clapperboard className="size-8" />} title="No projects yet">
          Make your first montage from the Dashboard or Auto Edit.
        </Empty>
      ) : (
        <ul className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {projects.data.map((p, i) => (
            <motion.li
              key={p.id}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: Math.min(i * 0.03, 0.3) }}
              className="panel overflow-hidden"
            >
              <button type="button" className="group block w-full text-left" onClick={() => navigate(`/projects/${p.id}`)} aria-label={`Open ${p.name}`}>
                <div className="relative aspect-video bg-black">
                  {p.latest_export?.thumb_url ? (
                    <img src={mediaUrl(p.latest_export.thumb_url)} alt="" className="size-full object-contain transition group-hover:scale-[1.02]" loading="lazy" />
                  ) : (
                    <div className="grid size-full place-items-center text-ink-500">
                      <Clapperboard className="size-10" aria-hidden />
                    </div>
                  )}
                  <span className="absolute top-2 left-2 inline-flex items-center gap-1.5 rounded-lg bg-black/70 px-2 py-1 text-xs font-semibold text-white">
                    <span className="text-cyber [&_svg]:size-3.5">{presetIcon(p.settings.preset)}</span>
                    {titleCase(p.settings.preset)}
                  </span>
                </div>
              </button>
              <div className="flex items-start gap-2 p-3.5">
                <div className="min-w-0 flex-1">
                  <h2 className="truncate font-bold text-white">{p.name}</h2>
                  <div className="mt-1 flex flex-wrap gap-1.5">
                    <Badge>{p.settings.aspect}</Badge>
                    {p.timeline ? (
                      <>
                        <Badge tone="cyan">{p.timeline.clips.length} clips</Badge>
                        <Badge>{formatDuration(timelineDuration(p.timeline))}</Badge>
                      </>
                    ) : (
                      <Badge tone="amber">Not edited yet</Badge>
                    )}
                    <span className="text-xs text-ink-400">{timeAgo(p.updated_at)}</span>
                  </div>
                </div>
                <IconButton label={`Open ${p.name}`} onClick={() => navigate(`/projects/${p.id}`)}>
                  <FolderOpen className="size-4" />
                </IconButton>
                <IconButton
                  label={`Rename ${p.name}`}
                  onClick={() => {
                    setRenaming(p);
                    setNewName(p.name);
                  }}
                >
                  <Pencil className="size-4" />
                </IconButton>
                <IconButton label={`Delete ${p.name}`} onClick={() => setDeleting(p)} className="hover:text-rose-400">
                  <Trash2 className="size-4" />
                </IconButton>
              </div>
            </motion.li>
          ))}
        </ul>
      )}

      <Modal open={!!renaming} onClose={() => setRenaming(null)} title="Rename project">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            void rename();
          }}
        >
          <TextField label="Name" value={newName} onChange={setNewName} maxLength={200} />
          <div className="mt-5 flex justify-end gap-2">
            <Button variant="ghost" onClick={() => setRenaming(null)}>
              Cancel
            </Button>
            <Button type="submit" variant="primary" loading={busy} disabled={!newName.trim()}>
              Rename
            </Button>
          </div>
        </form>
      </Modal>
      <ConfirmDialog
        open={!!deleting}
        title="Delete project?"
        message={
          <>
            Delete <strong className="text-white">{deleting?.name}</strong> and all of its rendered exports? Your uploaded clips stay in the library.
            This cannot be undone.
          </>
        }
        onConfirm={remove}
        onCancel={() => setDeleting(null)}
        busy={busy}
      />
    </div>
  );
}
