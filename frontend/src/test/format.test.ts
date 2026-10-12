import { describe, expect, it } from "vitest";
import { durationToSeconds, secondsToDuration } from "../components/DurationPicker";
import { formatBytes, formatDuration, formatEta, formatLabel, formatResolution, formatSeconds, timeAgo } from "../lib/format";

describe("format helpers", () => {
  it("formats durations", () => {
    expect(formatDuration(0)).toBe("0:00");
    expect(formatDuration(16.267)).toBe("0:16");
    expect(formatDuration(125)).toBe("2:05");
    expect(formatDuration(3725)).toBe("1:02:05");
    expect(formatDuration(null)).toBe("--:--");
    expect(formatDuration(Number.NaN)).toBe("--:--");
    expect(formatSeconds(2.577)).toBe("2.6s");
  });

  it("formats bytes", () => {
    expect(formatBytes(512)).toBe("512 B");
    expect(formatBytes(1536)).toBe("1.5 KB");
    expect(formatBytes(10927768)).toBe("10 MB");
    expect(formatBytes(5 * 1024 ** 3)).toBe("5.0 GB");
    expect(formatBytes(undefined)).toBe("-");
  });

  it("formats ETA, resolution, labels and relative time", () => {
    expect(formatEta(null)).toBe("estimating…");
    expect(formatEta(0)).toBe("almost done");
    expect(formatEta(12.4)).toBe("~12s left");
    expect(formatEta(95)).toBe("~1m 35s left");
    expect(formatResolution(1920, 1080)).toBe("1920×1080");
    expect(formatResolution(0, 0)).toBe("-");
    expect(formatLabel("mp4_h264")).toBe("MP4 (H.264)");
    expect(formatLabel("gif")).toBe("GIF");
    const now = Date.parse("2026-10-12T10:00:00Z");
    expect(timeAgo("2026-10-12T09:59:30Z", now)).toBe("just now");
    expect(timeAgo("2026-10-12T09:40:00Z", now)).toBe("20m ago");
    expect(timeAgo("2026-10-10T10:00:00Z", now)).toBe("2d ago");
  });

  it("maps target duration choices", () => {
    expect(durationToSeconds("auto")).toBeNull();
    expect(durationToSeconds("60")).toBe(60);
    expect(secondsToDuration(null)).toBe("auto");
    expect(secondsToDuration(120)).toBe("120");
  });
});
