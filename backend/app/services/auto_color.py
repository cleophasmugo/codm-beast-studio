"""AutoColorCorrector: measures exposure/contrast/saturation and picks conservative fixes."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

import numpy as np

from .video_analysis import FrameSamples


@dataclass
class ColorStats:
    brightness: float
    contrast: float
    saturation: float
    sharpness: float
    noise: float
    clip_low: float
    clip_high: float

    @classmethod
    def from_samples(cls, s: FrameSamples) -> ColorStats:
        def med(a: np.ndarray, default: float) -> float:
            return float(np.median(a)) if len(a) else default
        return cls(brightness=med(s.brightness, 0.45), contrast=med(s.contrast, 0.2),
                   saturation=med(s.saturation, 0.35), sharpness=med(s.sharpness, 300.0),
                   noise=med(s.noise, 0.01), clip_low=med(s.clip_low, 0.0), clip_high=med(s.clip_high, 0.0))

    @classmethod
    def from_dict(cls, d: dict) -> ColorStats:
        return cls(**{k: float(d.get(k, v)) for k, v in asdict(cls(0.45, 0.2, 0.35, 300.0, 0.01, 0, 0)).items()})


@dataclass
class ColorCorrection:
    brightness: float = 0.0  # eq brightness (-1..1)
    contrast: float = 1.0
    saturation: float = 1.0
    gamma: float = 1.0
    sharpen: float = 0.0  # unsharp luma amount
    denoise: bool = False
    reasons: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {k: (round(v, 3) if isinstance(v, float) else v) for k, v in asdict(self).items()}


class AutoColorCorrector:
    """Targets: mid exposure, moderate contrast, lively-but-natural saturation. All moves are clamped."""

    TARGET_BRIGHTNESS = 0.46
    TARGET_CONTRAST = 0.22
    TARGET_SATURATION = 0.42

    def correct(self, st: ColorStats) -> ColorCorrection:
        c = ColorCorrection()
        # Exposure: gamma for midtones (keeps blacks/whites), small brightness offset only when far off.
        diff = self.TARGET_BRIGHTNESS - st.brightness
        if abs(diff) > 0.04:
            c.gamma = float(np.clip(1.0 + diff * 1.6, 0.8, 1.35))
            c.reasons.append(f"{'lifted' if diff > 0 else 'lowered'} midtones (measured exposure {st.brightness:.2f})")
            if abs(diff) > 0.15:
                c.brightness = float(np.clip(diff * 0.25, -0.06, 0.06))
        # Contrast: add when flat, never when highlights or shadows already clip.
        if st.contrast < self.TARGET_CONTRAST - 0.02 and st.clip_high < 0.02 and st.clip_low < 0.05:
            c.contrast = float(np.clip(self.TARGET_CONTRAST / max(st.contrast, 0.05), 1.0, 1.2))
            c.reasons.append(f"added contrast (flat footage, spread {st.contrast:.2f})")
        elif st.clip_high > 0.04 or st.clip_low > 0.08:
            c.contrast = 0.95
            c.reasons.append("eased contrast to protect clipped highlights/shadows")
        # Saturation
        if st.saturation < self.TARGET_SATURATION:
            c.saturation = float(np.clip(self.TARGET_SATURATION / max(st.saturation, 0.08), 1.0, 1.3))
            c.reasons.append(f"boosted colour (saturation {st.saturation:.2f})")
        elif st.saturation > 0.65:
            c.saturation = 0.92
            c.reasons.append("toned down oversaturated colour")
        # Noise first, then sharpen (less on already-crisp footage, none on noisy footage).
        c.denoise = st.noise > 0.018
        if c.denoise:
            c.reasons.append("light denoise (grainy footage)")
        if st.sharpness < 150:
            c.sharpen = 0.8
        elif st.sharpness < 600:
            c.sharpen = 0.5
        else:
            c.sharpen = 0.25
        if c.denoise:
            c.sharpen = min(c.sharpen, 0.35)
        c.reasons.append(f"sharpen {c.sharpen:.2f} (detail score {st.sharpness:.0f})")
        return c
