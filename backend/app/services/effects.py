"""EffectsComposer: builds FFmpeg filter chains for colour grading, effects and transitions.

All values are numbers produced by our own code (clamped), never raw user strings.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..schemas import Clip, ProjectSettings
from .auto_color import ColorCorrection

# Look = (colorbalance args, contrast multiplier, saturation multiplier, extra filters)
LOOKS: dict[str, tuple[dict[str, float], float, float, list[str]]] = {
    "none": ({}, 1.0, 1.0, []),
    "beast": ({"rs": -0.05, "gs": 0.02, "bs": 0.05, "rh": 0.06, "gh": 0.02, "bh": -0.06}, 1.08, 1.12, []),
    "cinematic": ({"rs": -0.07, "gs": -0.01, "bs": 0.09, "rh": 0.09, "gh": 0.02, "bh": -0.07}, 1.05, 0.9, []),
    "esports": ({"bm": 0.02, "rh": 0.02}, 1.06, 1.15, []),
    "clean": ({}, 1.02, 1.04, []),
    "neon": ({"rs": 0.08, "bs": 0.14, "rm": 0.04, "bm": 0.1, "gh": -0.05, "bh": 0.04}, 1.1, 1.25, []),
    "warm": ({"rm": 0.07, "bm": -0.06, "rh": 0.04}, 1.03, 1.05, []),
    "cold": ({"rm": -0.05, "bm": 0.07, "bs": 0.04}, 1.03, 1.0, []),
    "vintage": ({"rs": 0.05, "bh": -0.06}, 0.95, 0.85, ["curves=preset=vintage"]),
    "bw": ({}, 1.1, 0.0, []),
}


def f(x: float) -> str:
    """Compact number formatting for filter arguments."""
    s = f"{float(x):.4f}".rstrip("0").rstrip(".")
    return "0" if s in ("", "-0") else s


@dataclass
class Frame:
    w: int
    h: int
    fps: int


class EffectsComposer:
    def __init__(self, settings: ProjectSettings):
        self.s = settings

    # ------------------------------------------------------------------ grading
    def grade(self, corr: ColorCorrection | None) -> list[str]:
        s = self.s
        e = s.effects
        corr = corr if (corr and e.auto_enhance) else ColorCorrection()
        man = s.color
        look_cb, look_c, look_s, extra = LOOKS.get(s.look, LOOKS["none"])
        k = s.look_strength
        brightness = man.brightness if man.brightness is not None else corr.brightness
        contrast = (man.contrast if man.contrast is not None else corr.contrast) * (1 + (look_c - 1) * k)
        saturation = (man.saturation if man.saturation is not None else corr.saturation) * (1 + (look_s - 1) * k)
        gamma = man.gamma if man.gamma is not None else corr.gamma
        # Auto-enhance and the look multiply; cap the result so already-vivid game footage doesn't go garish.
        contrast = min(max(contrast, 0.5), 1.4)
        saturation = min(max(saturation, 0.0), 1.3 if man.saturation is None else 1.8)
        chain: list[str] = []
        if e.denoise and corr.denoise:
            chain.append("hqdn3d=1.5:1.5:6:6")
        if any(abs(v) > 1e-3 for v in (brightness, contrast - 1, saturation - 1, gamma - 1)):
            chain.append(f"eq=brightness={f(brightness)}:contrast={f(contrast)}:saturation={f(saturation)}"
                         f":gamma={f(gamma)}")
        if abs(man.shadows) > 1e-3 or abs(man.highlights) > 1e-3:
            chain.append(f"curves=all='0/0 0.25/{f(0.25 + man.shadows)} 0.75/{f(0.75 + man.highlights)} 1/1'")
        if look_cb and k > 0:
            chain.append("colorbalance=" + ":".join(f"{kk}={f(v * k)}" for kk, v in look_cb.items()))
        chain += extra
        if e.sharpen:
            amt = man.sharpen_amount if man.sharpen_amount is not None else corr.sharpen
            amt = min(max(amt, 0.0), 1.2)
            if amt > 0.01:
                chain.append(f"unsharp=5:5:{f(amt)}:5:5:0")
        return chain

    # ------------------------------------------------------------------ per-clip finishing
    def finish(self, clip: Clip, out_dur: float, fr: Frame, is_first: bool, is_last: bool,
               peak_out: float | None = None, hits_out: list[float] | None = None) -> list[str]:
        """Effects and transition-in for one clip, already at fr.w x fr.h."""
        e = self.s.effects
        W, H = fr.w, fr.h
        chain: list[str] = []
        if clip.reaction:  # the punchline plays exactly as the user recorded it
            if is_last:
                d = min(0.5, out_dur / 4)
                chain.append(f"fade=t=out:st={f(max(0.0, out_dur - d))}:d={f(d)}")
            return chain
        hits = [h for h in (hits_out or []) if 0 <= h <= out_dur] if e.impact else []
        if hits:
            # Kill impact: a hard white pop and a violent shake that dies out fast, on every kill.
            a = max(6, int(min(W, H) * 0.02)) * 2
            env = "+".join(f"exp(-9*abs(t-{f(h)}))" for h in hits)
            chain.append(f"crop={W - 2 * a}:{H - 2 * a}:x='{a}+{a}*sin(t*61)*min(1,{env})'"
                         f":y='{a}+{a}*cos(t*53)*min(1,{env})'")
            chain.append(f"scale={W}:{H}")
            pop = "+".join(f"max(0,1-abs(t-{f(h)})/0.1)" for h in hits)
            chain.append(f"eq=brightness='0.4*min(1,{pop})':contrast='1+0.25*min(1,{pop})':eval=frame")
        zoom = 0.0
        # Effects stay short and light: big zooms, colour fringing and white-outs read as glitches, not style.
        if clip.transition == "zoom":
            zoom = 0.14
        elif clip.punch_in and e.punch_in:
            zoom = 0.07
        if zoom:
            chain.append(f"scale=w='trunc(iw*(1+{f(zoom)}*pow(max(0,1-t/0.35),2))/2)*2':h=-2:eval=frame")
            chain.append(f"crop={W}:{H}")
        if clip.shake and e.shake and not hits:
            a = max(4, int(min(W, H) * 0.012)) * 2
            p = peak_out if peak_out is not None else 0.0
            chain.append(f"crop={W - 2 * a}:{H - 2 * a}:x='{a}+{a}*sin(t*47)*exp(-4*abs(t-{f(p)}))'"
                         f":y='{a}+{a}*cos(t*39)*exp(-4*abs(t-{f(p)}))'")
            chain.append(f"scale={W}:{H}")
        if clip.transition == "glitch":
            shift = max(2, W // 320)
            chain.append(f"rgbashift=rh=-{shift}:bh={shift}:enable='lt(t,0.12)'")
            chain.append("noise=alls=6:allf=t:enable='lt(t,0.1)'")
        elif e.chromatic and clip.transition in ("flash", "zoom"):
            shift = max(1, W // 640)
            chain.append(f"rgbashift=rh=-{shift}:bh={shift}:enable='lt(t,0.1)'")
        if clip.transition == "whip":
            chain.append("gblur=sigma=40:sigmaV=0.5:steps=2:enable='lt(t,0.14)'")
        if e.motion_blur and clip.kind == "video":
            chain.append("tmix=frames=2:weights='1 1'")
        if e.vignette:
            chain.append("vignette=angle=0.5")
        if e.letterbox and H < W * 0.75:
            bar = int(H * 0.12)
            chain.append(f"drawbox=x=0:y=0:w=iw:h={bar}:color=black:t=fill")
            chain.append(f"drawbox=x=0:y=ih-{bar}:w=iw:h={bar}:color=black:t=fill")
        if clip.transition == "flash" or (e.flash and clip.transition == "zoom"):
            # A quick brightness pop, not a full white frame.
            chain.append("eq=brightness='0.3*max(0,1-t/0.18)':eval=frame")
        elif clip.transition == "fade" or (is_first and clip.transition not in ("cut",)):
            chain.append("fade=t=in:st=0:d=0.35")
        if is_last:
            d = min(0.8, out_dur / 3)
            chain.append(f"fade=t=out:st={f(max(0.0, out_dur - d))}:d={f(d)}")
        return chain

    def glow(self) -> bool:
        return self.s.effects.glow

    def light_leak(self, clip: Clip) -> bool:
        return self.s.effects.light_leaks and clip.transition in ("fade", "flash", "zoom")
