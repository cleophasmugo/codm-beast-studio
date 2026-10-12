"""Example game-event detector plugin (template, not shipped as a trained model).

CODM Beast Studio never claims to recognise kills on its own. To add real event recognition,
train a model on your own labelled CODM recordings and wrap it like this, then set:

    BEAST_DETECTOR_PLUGINS=my_detectors.kill_feed:KillFeedDetector

(the module must be importable by the API and the worker, e.g. installed with pip or placed on
PYTHONPATH). Events with confidence >= 0.6 boost nearby highlights and are shown in the UI as
"kill (KillFeedDetector, 87%)" instead of a heuristic guess.
"""

from __future__ import annotations

from pathlib import Path

from app.services.detectors import DetectedEvent


class KillFeedDetector:
    name = "KillFeedDetector"

    def __init__(self) -> None:
        # Load your model once, e.g.:
        #   import torch
        #   self.model = torch.jit.load("/models/killfeed.pt").eval()
        self.model = None

    def detect(self, video_path: Path, duration: float) -> list[DetectedEvent]:
        if self.model is None:
            return []  # no model configured: report nothing rather than guessing
        events: list[DetectedEvent] = []
        # Typical approach: decode ~5 fps, crop the kill-feed / hit-marker region of the HUD,
        # run the classifier, and emit one event per positive detection:
        #   events.append(DetectedEvent(time=t, label="kill", confidence=float(p), source=self.name))
        return events
