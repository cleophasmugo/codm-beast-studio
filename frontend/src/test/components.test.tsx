import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Job, Preset } from "../api";
import { JobProgressCard } from "../components/JobProgressCard";
import { PresetPicker } from "../components/PresetPicker";

const presets: Preset[] = [
  { id: "beast", label: "Beast Mode", description: "Hard cuts", aspect: "16:9", target_duration: 30 },
  { id: "tiktok", label: "TikTok Vertical", description: "Vertical", aspect: "9:16", target_duration: null },
];

function job(over: Partial<Job> = {}): Job {
  return {
    id: "j1", project_id: "p1", kind: "auto_edit", status: "running", stage: "Rendering", progress: 0.42,
    message: "Encoding clip 3 of 5", eta_seconds: 12, result: null, error: null, attempts: 1,
    created_at: "2026-10-12T09:00:00Z", started_at: null, finished_at: null, ...over,
  };
}

afterEach(() => vi.unstubAllGlobals());

describe("PresetPicker", () => {
  it("renders presets as radios and reports the choice", () => {
    const onChange = vi.fn();
    render(<PresetPicker presets={presets} value="beast" onChange={onChange} />);
    const radios = screen.getAllByRole("radio");
    expect(radios).toHaveLength(2);
    expect(radios[0]).toHaveAttribute("aria-checked", "true");
    expect(screen.getByText("Auto length")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("radio", { name: /TikTok Vertical/ }));
    expect(onChange).toHaveBeenCalledWith("tiktok");
  });
});

describe("JobProgressCard", () => {
  it("polls the job, shows stage/progress/ETA and cancels", async () => {
    const calls: string[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string, init?: RequestInit) => {
        calls.push(`${init?.method ?? "GET"} ${url}`);
        const body = url.endsWith("/cancel") ? job({ status: "cancelled", stage: "", message: "Cancelled by user" }) : job();
        return new Response(JSON.stringify(body), { status: 200 });
      }),
    );
    render(<JobProgressCard jobId="j1" />);
    expect(await screen.findByText("Rendering")).toBeInTheDocument();
    expect(screen.getByText("42%")).toBeInTheDocument();
    expect(screen.getByText("~12s left")).toBeInTheDocument();
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "42");
    fireEvent.click(screen.getByRole("button", { name: /Cancel/ }));
    await waitFor(() => expect(calls).toContain("POST /api/jobs/j1/cancel"));
  });

  it("shows the error and a Retry button for failed jobs", async () => {
    const onFinish = vi.fn();
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) =>
        new Response(JSON.stringify(url.endsWith("/retry") ? job() : job({ status: "failed", error: "Video processing failed" })), { status: 200 }),
      ),
    );
    render(<JobProgressCard jobId="j1" onFinish={onFinish} />);
    expect(await screen.findByText("Video processing failed")).toBeInTheDocument();
    expect(onFinish).toHaveBeenCalledWith(expect.objectContaining({ status: "failed" }));
    const retry = screen.getByRole("button", { name: /Retry/ });
    fireEvent.click(retry);
    await waitFor(() => expect(fetch).toHaveBeenCalledWith("/api/jobs/j1/retry", expect.objectContaining({ method: "POST" })));
  });
});
