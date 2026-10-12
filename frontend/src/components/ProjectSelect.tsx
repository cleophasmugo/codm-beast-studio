import { FolderPlus } from "lucide-react";
import { useEffect } from "react";
import { api, type Project } from "../api";
import { useAsync } from "../lib/hooks";
import { navigate, setQueryParam, useLocation } from "../lib/router";
import { Button, Empty, ErrorBanner, SelectField, Spinner } from "./ui";

/** Project chooser bound to the ?project= query parameter. */
export function useSelectedProjectId(): string | null {
  const { query } = useLocation();
  return query.get("project");
}

export function ProjectSelect({
  onProjects,
  label = "Project",
}: {
  onProjects?: (p: Project[]) => void;
  label?: string;
}) {
  const selected = useSelectedProjectId();
  const projects = useAsync(() => api.listProjects(), []);
  useEffect(() => {
    if (projects.data) onProjects?.(projects.data);
    if (projects.data?.length && (!selected || !projects.data.some((p) => p.id === selected))) {
      setQueryParam("project", projects.data[0].id);
    }
  }, [projects.data, selected, onProjects]);

  if (projects.loading && !projects.data) return <Spinner label="Loading projects" />;
  if (projects.error) return <ErrorBanner onRetry={projects.reload}>{projects.error}</ErrorBanner>;
  if (!projects.data?.length)
    return (
      <Empty icon={<FolderPlus className="size-8" />} title="No projects yet">
        <p>Create a montage first, then come back to fine-tune it.</p>
        <Button className="mt-3" variant="primary" onClick={() => navigate("/auto-edit")}>
          Start an Auto Edit
        </Button>
      </Empty>
    );
  return (
    <SelectField
      label={label}
      value={selected ?? ""}
      onChange={(e) => setQueryParam("project", e.target.value)}
      className="w-full sm:max-w-sm"
    >
      {projects.data.map((p) => (
        <option key={p.id} value={p.id}>
          {p.name}
        </option>
      ))}
    </SelectField>
  );
}
