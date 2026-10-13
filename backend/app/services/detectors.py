"""Pluggable game-event detectors.

One detector is built in: `CodmKillNoticeDetector` spots the yellow "KNOCKED DOWN" / "ELIMINATED" /
"HEADSHOT" notice CODM shows right of centre after each of your kills. It reads colour and position
only (no OCR, no model), so it is labelled as a HUD detector with a fixed confidence.

A trained model (for example a PyTorch kill-feed detector) can be added by implementing
`EventDetector` and listing it in BEAST_DETECTOR_PLUGINS as "my_package.my_module:MyDetector".
Every event is shown with its detector's name and confidence, so the UI can tell detected game
events apart from the motion/sound heuristics.
"""

from __future__ import annotations

import importlib
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from ..core.config import get_settings

log = logging.getLogger(__name__)


@dataclass
class DetectedEvent:
    time: float
    label: str  # e.g. "kill", "headshot", "multi_kill"
    confidence: float  # 0..1
    source: str  # detector name


@runtime_checkable
class EventDetector(Protocol):
    name: str

    def detect(self, video_path: Path, duration: float) -> list[DetectedEvent]: ...


class CodmKillNoticeDetector:
    """Finds the moment CODM's yellow kill notice pops up right of the crosshair.

    The notice ("KNOCKED DOWN", "ELIMINATED", "HEADSHOT") is saturated yellow text in a fixed HUD
    spot. A kill is the frame where enough yellow text strokes appear in that spot after at least
    QUIET seconds without them; the notice lingers about a second, so one kill is reported once.
    """

    name = "CODM kill notice"
    SAMPLE_FPS = 5.0
    ROI = (0.33, 0.50, 0.64, 0.96)  # top, bottom, left, right as fractions of the frame
    HSV_LO, HSV_HI = (22, 110, 170), (36, 255, 255)  # CODM notice yellow
    ON_PCT, OFF_PCT = 1.0, 0.6  # % of ROI pixels that are notice-yellow
    MIN_STROKES = 8  # text is many small strokes; a yellow car or sunlit wall is one big blob
    QUIET = 0.6  # seconds without the notice before a new one counts
    CONFIDENCE = 0.85

    def measure(self, frame: Any) -> tuple[float, int]:
        import cv2
        h, w = frame.shape[:2]
        t, b, lft, r = self.ROI
        roi = frame[int(h * t):int(h * b), int(w * lft):int(w * r)]
        mask = cv2.inRange(cv2.cvtColor(roi, cv2.COLOR_BGR2HSV), self.HSV_LO, self.HSV_HI)
        _, _, stats, _ = cv2.connectedComponentsWithStats(mask)
        limit = max(4, mask.size // 120)  # bigger than any letter, smaller than a yellow car
        strokes = sum(1 for s in stats[1:] if 3 <= s[cv2.CC_STAT_AREA] <= limit)
        return float(mask.mean() / 255 * 100), strokes

    def detect_series(self, series: list[tuple[float, float, int]]) -> list[DetectedEvent]:
        """series: (time, yellow %, stroke count) samples in time order."""
        events: list[DetectedEvent] = []
        last_on = -1e9
        for t, pct, strokes in series:
            on = pct >= self.ON_PCT and strokes >= self.MIN_STROKES
            if on and t - last_on >= self.QUIET:
                events.append(DetectedEvent(time=round(t, 2), label="kill", confidence=self.CONFIDENCE,
                                            source=self.name))
            if on or pct >= self.OFF_PCT:
                last_on = t
        return events

    def detect(self, video_path: Path, duration: float) -> list[DetectedEvent]:
        import cv2
        cap = cv2.VideoCapture(str(video_path))
        try:
            fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
            step = max(1, round(fps / self.SAMPLE_FPS))
            series: list[tuple[float, float, int]] = []
            i = 0
            while cap.grab():
                if i % step == 0:
                    ok, frame = cap.retrieve()
                    if ok:
                        series.append((i / fps, *self.measure(frame)))
                i += 1
        finally:
            cap.release()
        return self.detect_series(series)


def load_detectors() -> list[EventDetector]:
    out: list[EventDetector] = [CodmKillNoticeDetector()] if get_settings().codm_kill_detector else []
    spec = get_settings().detector_plugins.strip()
    for entry in filter(None, (s.strip() for s in spec.split(","))):
        try:
            mod_name, cls_name = entry.split(":", 1)
            cls = getattr(importlib.import_module(mod_name), cls_name)
            det = cls()
            if isinstance(det, EventDetector):
                out.append(det)
            else:
                log.warning("Detector %s does not implement EventDetector; ignored", entry)
        except Exception:  # a broken plugin must never break the heuristic pipeline
            log.exception("Could not load detector plugin %s; continuing without it", entry)
    return out


def run_detectors(video_path: Path, duration: float, min_confidence: float = 0.6) -> list[DetectedEvent]:
    events: list[DetectedEvent] = []
    for det in load_detectors():
        try:
            events += [e for e in det.detect(video_path, duration) if e.confidence >= min_confidence]
        except Exception:
            log.exception("Detector %s failed; ignoring its output", getattr(det, "name", det))
    return events
