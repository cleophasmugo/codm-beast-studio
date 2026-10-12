/** Client-side undo/redo history for timeline edits (a plain reducer, unit tested). */
import type { Timeline } from "../api";

export interface HistoryState {
  past: Timeline[];
  present: Timeline | null;
  future: Timeline[];
  /** True when present differs from the last saved/loaded version. */
  dirty: boolean;
}

export type HistoryAction =
  | { type: "load"; timeline: Timeline | null }
  | { type: "edit"; update: (t: Timeline) => Timeline }
  | { type: "undo" }
  | { type: "redo" }
  | { type: "saved" };

export const HISTORY_LIMIT = 100;

export const initialHistory: HistoryState = { past: [], present: null, future: [], dirty: false };

export function historyReducer(state: HistoryState, action: HistoryAction): HistoryState {
  switch (action.type) {
    case "load":
      return { past: [], present: action.timeline, future: [], dirty: false };
    case "edit": {
      if (!state.present) return state;
      const next = action.update(state.present);
      if (next === state.present) return state;
      return {
        past: [...state.past, state.present].slice(-HISTORY_LIMIT),
        present: next,
        future: [],
        dirty: true,
      };
    }
    case "undo": {
      if (!state.past.length || !state.present) return state;
      const prev = state.past[state.past.length - 1];
      return { past: state.past.slice(0, -1), present: prev, future: [state.present, ...state.future], dirty: true };
    }
    case "redo": {
      if (!state.future.length || !state.present) return state;
      const [next, ...rest] = state.future;
      return { past: [...state.past, state.present], present: next, future: rest, dirty: true };
    }
    case "saved":
      return { ...state, dirty: false };
    default:
      return state;
  }
}

/** Immutable helpers used by the editor. */
export function moveItem<T>(list: T[], from: number, to: number): T[] {
  if (from === to || from < 0 || to < 0 || from >= list.length || to >= list.length) return list;
  const copy = list.slice();
  const [item] = copy.splice(from, 1);
  copy.splice(to, 0, item);
  return copy;
}
