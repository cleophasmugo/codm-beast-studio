import { describe, expect, it } from "vitest";
import type { Timeline } from "../api";
import { HISTORY_LIMIT, historyReducer, initialHistory, moveItem, type HistoryState } from "../lib/timelineHistory";

const tl = (n: number): Timeline => ({ version: 1, clips: [], overlays: [], music: null, bpm: n, notes: [] });
const setBpm = (n: number) => ({ type: "edit" as const, update: (t: Timeline) => ({ ...t, bpm: n }) });

describe("timeline history reducer", () => {
  it("records edits and supports undo/redo", () => {
    let s: HistoryState = historyReducer(initialHistory, { type: "load", timeline: tl(1) });
    expect(s.dirty).toBe(false);
    s = historyReducer(s, setBpm(2));
    s = historyReducer(s, setBpm(3));
    expect(s.present?.bpm).toBe(3);
    expect(s.dirty).toBe(true);
    s = historyReducer(s, { type: "undo" });
    expect(s.present?.bpm).toBe(2);
    s = historyReducer(s, { type: "undo" });
    expect(s.present?.bpm).toBe(1);
    expect(historyReducer(s, { type: "undo" })).toBe(s); // nothing left
    s = historyReducer(s, { type: "redo" });
    expect(s.present?.bpm).toBe(2);
    // a new edit clears the redo stack
    s = historyReducer(s, setBpm(9));
    expect(s.future).toHaveLength(0);
    expect(historyReducer(s, { type: "redo" })).toBe(s);
  });

  it("ignores no-op edits and edits before load", () => {
    expect(historyReducer(initialHistory, setBpm(1))).toBe(initialHistory);
    const s = historyReducer(initialHistory, { type: "load", timeline: tl(1) });
    expect(historyReducer(s, { type: "edit", update: (t) => t })).toBe(s);
  });

  it("marks saved and caps the history length", () => {
    let s = historyReducer(initialHistory, { type: "load", timeline: tl(0) });
    for (let i = 1; i <= HISTORY_LIMIT + 20; i++) s = historyReducer(s, setBpm(i));
    expect(s.past).toHaveLength(HISTORY_LIMIT);
    s = historyReducer(s, { type: "saved" });
    expect(s.dirty).toBe(false);
  });

  it("moves list items immutably", () => {
    const a = ["a", "b", "c"];
    expect(moveItem(a, 0, 2)).toEqual(["b", "c", "a"]);
    expect(moveItem(a, 2, 1)).toEqual(["a", "c", "b"]);
    expect(moveItem(a, 0, 5)).toBe(a);
    expect(a).toEqual(["a", "b", "c"]);
  });
});
