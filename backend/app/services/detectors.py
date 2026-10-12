"""Pluggable game-event detectors.

The built-in pipeline uses transparent heuristics only (motion, sound, scene changes) and never
claims to recognise game events. A trained model (for example a PyTorch CODM kill-feed detector)
can be added by implementing `EventDetector` and listing it in BEAST_DETECTOR_PLUGINS as
"my_package.my_module:MyDetector". Its events are shown with the model's name and confidence,
so the UI can tell model evidence apart from heuristic guesses.
"""

from __future__ import annotations

import importlib
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable

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


def load_detectors() -> list[EventDetector]:
    out: list[EventDetector] = []
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
