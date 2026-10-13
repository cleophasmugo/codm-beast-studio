"""HighlightAnalyzer: turns visual + audio signals into ranked candidate clips.

Every candidate carries the signals that made it score (so the UI can show *why*) and an
`evidence` field: "heuristic" for signal-based guesses, or the detector name when a
configured model actually reported an event.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
from scipy.ndimage import gaussian_filter1d
from scipy.signal import find_peaks

from ..schemas import HighlightWeights
from .audio_analysis import AudioFeatures
from .detectors import DetectedEvent
from .video_analysis import FrameSamples

GRID = 0.25  # seconds per analysis bin

REASONS = {
    "motion": "big on-screen motion",
    "flow": "fast camera movement",
    "audio": "loud moment",
    "transients": "burst of sharp sound spikes (gunfire-like)",
    "scene": "scene change",
    "flash": "bright flash",
}


@dataclass
class Candidate:
    media_id: str
    start: float
    end: float
    peak: float
    score: float
    excitement: float
    clarity: float
    reasons: list[str]
    signals: dict[str, float]
    evidence: str = "heuristic"
    events: list[dict] = field(default_factory=list)
    crop_x: float = 0.5

    def as_dict(self) -> dict[str, Any]:
        return {
            "media_id": self.media_id, "start": round(self.start, 3), "end": round(self.end, 3),
            "peak": round(self.peak, 3), "score": round(self.score, 4), "excitement": round(self.excitement, 4),
            "clarity": round(self.clarity, 4), "reasons": self.reasons,
            "signals": {k: round(v, 3) for k, v in self.signals.items()}, "evidence": self.evidence,
            "events": self.events, "crop_x": round(self.crop_x, 3),
        }


def _bin(times: np.ndarray, values: np.ndarray, n: int, how: str = "mean") -> np.ndarray:
    if len(values) == 0:
        return np.zeros(n)
    idx = np.clip((times / GRID).astype(int), 0, n - 1)
    if how == "max":
        # start from -inf, not 0: values can be negative (loudness in dB is always below 0)
        out = np.full(n, -np.inf)
        np.maximum.at(out, idx, values)
        filled = np.isfinite(out)
    else:
        out = np.zeros(n)
        sums = np.zeros(n)
        cnt = np.zeros(n)
        np.add.at(sums, idx, values)
        np.add.at(cnt, idx, 1)
        filled = cnt > 0
        out[filled] = sums[filled] / cnt[filled]
    if (~filled).any() and filled.any():  # interpolate empty bins
        out[~filled] = np.interp(np.where(~filled)[0], np.where(filled)[0], out[filled])
    return out


def robust_z(x: np.ndarray, min_scale: float = 0.0) -> np.ndarray:
    if len(x) == 0:
        return x
    med = np.median(x)
    mad = np.median(np.abs(x - med)) * 1.4826
    scale = mad if mad > 1e-9 else (np.std(x) if np.std(x) > 1e-9 else 1.0)
    return (x - med) / max(scale, min_scale)


# Smallest spread treated as meaningful per signal. Without it a signal that is nearly constant
# (steady footage has almost no frame-to-frame brightening) turns every tiny wobble into a "spike".
MIN_SCALE = {"flash": 0.01, "audio": 1.5}  # brightness units (0..1) and dB


class HighlightAnalyzer:
    PACING = {
        # fast montages want several short, distinct hits per fight; slow edits want whole moments
        "fast": {"pre_roll": 1.0, "post_roll": 0.9, "max_len": 5.0, "min_peak_gap": 1.3},
        "slow": {"pre_roll": 1.75, "post_roll": 1.5, "max_len": 8.0, "min_peak_gap": 2.5},
    }

    @classmethod
    def for_pacing(cls, weights: HighlightWeights | None, beats_per_clip: int) -> HighlightAnalyzer:
        return cls(weights, **cls.PACING["fast" if beats_per_clip <= 2 else "slow"])

    def __init__(self, weights: HighlightWeights | None = None, pre_roll: float = 1.75,
                 post_roll: float = 1.5, max_len: float = 8.0, min_peak_gap: float = 2.5):
        self.w = weights or HighlightWeights()
        self.pre_roll = pre_roll
        self.post_roll = post_roll
        self.max_len = max_len
        self.min_peak_gap = min_peak_gap

    # ------------------------------------------------------------------ signals
    def signals(self, duration: float, vs: FrameSamples, au: AudioFeatures) -> dict[str, np.ndarray]:
        n = max(1, int(np.ceil(duration / GRID)))
        t = vs.times
        bright = vs.brightness
        flash = np.maximum(0.0, np.diff(bright, prepend=bright[:1] if len(bright) else 0))
        sig = {
            "motion": _bin(t, vs.motion, n),
            "flow": _bin(t, vs.flow, n),
            "scene": _bin(t, vs.hist_diff, n, "max"),
            "flash": _bin(t, flash, n, "max"),
            "sharpness": _bin(t, vs.sharpness, n),
            "brightness": _bin(t, vs.brightness, n),
            "centroid": _bin(t, vs.centroid_x, n),
        }
        if au.empty:
            sig["audio"] = np.zeros(n)
            sig["transients"] = np.zeros(n)
        else:
            at = np.arange(len(au.rms_db)) / au.frame_rate
            sig["audio"] = _bin(at, au.rms_db, n, "max")
            tr = np.zeros(n)
            for tt in au.transient_times:
                k = int(tt / GRID)
                if 0 <= k < n:
                    tr[k] += 1
            # density of transients over ~1 s windows: bursts of shots score higher than a lone click
            sig["transients"] = gaussian_filter1d(tr, 2.0) * 4
        return sig

    def excitement(self, sig: dict[str, np.ndarray]) -> tuple[np.ndarray, dict[str, np.ndarray]]:
        parts: dict[str, np.ndarray] = {}
        for key in ("motion", "flow", "audio", "transients", "scene", "flash"):
            z = robust_z(sig[key], MIN_SCALE.get(key, 0.0))
            parts[key] = np.clip(z, 0, 4) / 4.0
        w = self.w
        weights = {"motion": w.motion, "flow": w.motion * 0.6, "audio": w.audio, "transients": w.transients,
                   "scene": w.scene, "flash": w.flash}
        total = sum(weights.values()) or 1.0
        e = sum(parts[k] * weights[k] for k in parts) / total
        e = gaussian_filter1d(e, 2.0)  # ~0.5 s smoothing
        return e, parts

    # ------------------------------------------------------------------ candidates
    def candidates(self, media_id: str, duration: float, vs: FrameSamples, au: AudioFeatures,
                   cuts: list[float], events: list[DetectedEvent] | None = None) -> tuple[list[Candidate], dict]:
        sig = self.signals(duration, vs, au)
        e, parts = self.excitement(sig)
        events = events or []
        for ev in events:  # model events add a strong, explicit bump
            k = int(ev.time / GRID)
            if 0 <= k < len(e):
                e[max(0, k - 4):k + 4] += 0.5 * ev.confidence
        sharp_z = np.clip(robust_z(np.log1p(sig["sharpness"])), -3, 3)
        exposure_ok = 1.0 - np.clip(np.abs(sig["brightness"] - 0.45) * 2.5, 0, 1)
        clarity = np.clip(0.5 + sharp_z / 6, 0, 1) * 0.6 + exposure_ok * 0.4

        if len(e) < 3 or float(e.max()) <= 1e-6:
            return [], self._summary(e, sig, au, cuts)
        prom = max(0.02, float(np.std(e)) * 0.5)
        peaks, _ = find_peaks(e, distance=max(1, int(self.min_peak_gap / GRID)), prominence=prom)
        floor = float(np.percentile(e, 60))
        windows: list[tuple[float, float, int]] = []
        for p in peaks:
            if e[p] >= floor:
                st, en = self._context_window((p + 0.5) * GRID, e, cuts, duration)
                windows.append((st, en, int(p)))
        # Sustained fights: tile long high-action stretches into several distinct hits,
        # so one long gunfight can supply more than one cut.
        seg_len = self.pre_roll + self.post_roll
        med, top = float(np.median(e)), float(e.max())
        active = np.append(e >= med + 0.45 * (top - med), False)
        r0 = None
        for i, on in enumerate(active):
            if on and r0 is None:
                r0 = i
            elif not on and r0 is not None:
                ra, rb = r0 * GRID, i * GRID
                r0 = None
                if rb - ra < seg_len * 1.6:
                    continue
                n_seg = int((rb - ra) // seg_len)
                for k in range(n_seg):
                    sa, sb = ra + k * seg_len, ra + (k + 1) * seg_len
                    if any(min(sb, w[1]) - max(sa, w[0]) > seg_len * 0.5 for w in windows):
                        continue
                    ia, ib = int(sa / GRID), max(int(sa / GRID) + 1, int(sb / GRID))
                    pk = ia + int(np.argmax(e[ia:ib]))
                    windows.append((round(sa, 3), round(min(sb, duration), 3), pk))
        cands: list[Candidate] = []
        for start, end, p in windows:
            peak_t = (p + 0.5) * GRID
            a, b = int(start / GRID), max(int(start / GRID) + 1, int(end / GRID))
            seg = e[a:b]
            exc = float(np.mean(np.sort(seg)[len(seg) // 2:])) if len(seg) else float(e[p])
            clar = float(np.mean(clarity[a:b])) if b > a else 0.5
            sigs = {k: float(parts[k][max(0, p - 2):p + 3].max()) for k in parts}
            reasons = [REASONS[k] for k, v in sorted(sigs.items(), key=lambda kv: -kv[1]) if v >= 0.35][:3]
            evs = [ev for ev in events if start <= ev.time <= end]
            if evs:
                reasons = [f"{ev.label} ({ev.source}, {ev.confidence:.0%})" for ev in evs] + reasons
            if not reasons:
                reasons = ["above-average action"]
            cands.append(Candidate(
                media_id=media_id, start=start, end=end, peak=peak_t,
                score=0.0, excitement=exc, clarity=clar, reasons=reasons, signals=sigs,
                evidence=evs[0].source if evs else "heuristic",
                events=[{"time": ev.time, "label": ev.label, "confidence": ev.confidence, "source": ev.source}
                        for ev in evs],
                crop_x=float(np.median(sig["centroid"][a:b])) if b > a else 0.5,
            ))
        # Normalised score: excitement dominates, clarity breaks ties.
        if cands:
            emax = max(c.excitement for c in cands) or 1.0
            for c in cands:
                c.score = (c.excitement / emax) * (1.0 - 0.25 * min(self.w.clarity, 1.0)) \
                    + c.clarity * 0.25 * min(self.w.clarity, 1.0)
        cands.sort(key=lambda c: -c.score)
        return cands, self._summary(e, sig, au, cuts)

    def _context_window(self, peak: float, e: np.ndarray, cuts: list[float], duration: float) -> tuple[float, float]:
        start = peak - self.pre_roll
        end = peak + self.post_roll
        # Include the build-up: walk back while excitement keeps rising toward the peak.
        k = int(start / GRID)
        while k > 0 and (peak - k * GRID) < self.max_len * 0.6 and e[k - 1] < e[k] and e[k] > np.median(e):
            k -= 1
        start = min(start, k * GRID)
        # Don't straddle a hard cut: a clip shouldn't open with a sliver of the previous scene.
        for c in cuts:
            if start < c < peak - 0.3:
                start = c + 0.05
            if peak + 0.3 < c < end:
                end = c - 0.05
                break
        start = max(0.0, start)
        end = min(duration, max(end, peak + 0.5))
        if end - start > self.max_len:
            start = max(0.0, peak - self.max_len * 0.6)
            end = min(duration, start + self.max_len)
        return round(start, 3), round(end, 3)

    def _summary(self, e: np.ndarray, sig: dict[str, np.ndarray], au: AudioFeatures, cuts: list[float]) -> dict:
        quiet: list[list[float]] = []
        if len(e):
            med = float(np.median(e))
            mask = e <= med + 0.15 * (float(e.max()) - med)
            start = None
            for i, m in enumerate(np.append(mask, False)):
                if m and start is None:
                    start = i
                elif not m and start is not None:
                    if (i - start) * GRID >= 3.0:
                        quiet.append([round(start * GRID, 2), round(i * GRID, 2)])
                    start = None
        step = max(1, len(e) // 400)
        return {
            "grid": GRID * step,
            "curve": [round(float(v), 4) for v in e[::step]],
            "scene_cuts": cuts,
            "quiet_sections": quiet,
            "silences": [list(s) for s in au.silences],
            "transient_count": len(au.transient_times),
            "centroid": [round(float(v), 3) for v in sig["centroid"]],
        }
