"""FFmpegRenderer: renders a Timeline to a finished video.

Stage 1 renders each clip to an intermediate (same size, fps and codec, PCM audio) with its
reframe, grade, effects and transition baked in. Stage 2 concatenates them losslessly, then
one final pass adds overlays, music (with ducking), sound effects and loudness normalisation,
and encodes the export format.
"""

from __future__ import annotations

import logging
import math
import shutil
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageFilter, ImageOps

from ..schemas import Clip, ImageEdit, Overlay, ProjectSettings, Timeline
from . import graphics
from .auto_color import ColorCorrection
from .effects import EffectsComposer, Frame, f
from .export import OutputSpec
from .ffmpeg import ffprobe_json, run_ffmpeg
from .image_studio import apply_edit
from .sound_library import build_sfx_bed

log = logging.getLogger(__name__)
IRIS_SECONDS = 1.0  # length of the scope-circle intro
LOW_RES_HEIGHT = 720  # sources below this get deblocking before upscaling and extra sharpening after

StageProgress = Callable[[float, str], None]


@dataclass
class SourceMedia:
    id: str
    kind: str
    path: Path
    info: dict
    color: ColorCorrection | None = None
    source: str = "upload"  # upload | library | image_studio


class RenderError(RuntimeError):
    pass


class FFmpegRenderer:
    def __init__(self, settings: ProjectSettings, spec: OutputSpec, work: Path, media: dict[str, SourceMedia],
                 assets_dir: Path, on_progress: StageProgress | None = None,
                 should_cancel: Callable[[], bool] | None = None, x264_preset: str = "veryfast",
                 preview: bool = False):
        self.s = settings
        self.spec = spec
        self.work = work
        self.media = media
        self.assets = assets_dir
        self.on_progress = on_progress or (lambda p, m: None)
        self.should_cancel = should_cancel
        self.fx = EffectsComposer(settings)
        self.frame = Frame(spec.width, spec.height, spec.fps)
        self.x264_preset = "ultrafast" if preview else x264_preset
        self.preview = preview
        work.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ public
    def render(self, tl: Timeline, out_path: Path) -> dict:
        clips = [c for c in tl.clips if self._usable(c)]
        if not clips:
            raise RenderError("The timeline has no playable clips.")
        fps = self.spec.fps
        bounds = [0]
        acc = 0.0
        for c in clips:
            acc += c.output_duration()
            bounds.append(int(round(acc * fps)))
        frames = [max(1, b - a) for a, b in zip(bounds, bounds[1:])]
        total = sum(frames) / fps
        overlays = self._overlays(tl, total)
        copy_video = (not overlays and self.spec.format == "mp4_h264" and not self.preview)
        inter_crf = self._final_crf() if copy_video else self.spec.intermediate_crf
        parts: list[Path] = []
        weight_clips = 0.75
        for i, (c, n) in enumerate(zip(clips, frames)):
            out = self.work / f"clip_{i:03d}.mkv"
            self._render_clip(c, n, out, is_first=i == 0, is_last=i == len(clips) - 1, crf=inter_crf,
                              progress=lambda sec, i=i, n=n: self.on_progress(
                                  weight_clips * (i + min(1.0, sec * fps / n)) / len(clips),
                                  f"Rendering clip {i + 1} of {len(clips)}"))
            parts.append(out)
        lst = self.work / "concat.txt"
        lst.write_text("".join(f"file '{p.name}'\n" for p in parts))
        boundaries = [b / fps for b in bounds]
        self._final(lst, clips, boundaries, total, overlays, tl, out_path, copy_video)
        info = ffprobe_json(out_path)
        v = next((s for s in info.get("streams", []) if s.get("codec_type") == "video"), {})
        return {
            "width": int(v.get("width", self.spec.width)), "height": int(v.get("height", self.spec.height)),
            "duration": float(info.get("format", {}).get("duration", total)), "fps": fps,
            "format": self.spec.format, "size_bytes": out_path.stat().st_size,
            "clip_boundaries": [round(b, 3) for b in boundaries],
        }

    # ------------------------------------------------------------------ helpers
    def _final_crf(self) -> int:
        a = self.spec.video_args
        return int(a[a.index("-crf") + 1]) if "-crf" in a else self.spec.intermediate_crf

    def _usable(self, c: Clip) -> bool:
        if c.kind == "card":
            return c.duration > 0.1
        m = self.media.get(c.media_id or "")
        if not m:
            return False
        if c.kind == "image":
            return c.duration > 0.1 and m.kind in ("image", "sticker")
        return m.kind == "video" and c.end - c.start > 0.1

    def _encode_args(self, crf: int, n_frames: int) -> list[str]:
        fps = self.spec.fps
        return ["-frames:v", str(n_frames), "-t", f"{n_frames / fps:.6f}", "-r", str(fps),
                "-c:v", "libx264", "-preset", self.x264_preset, "-crf", str(crf), "-pix_fmt", "yuv420p",
                "-g", str(fps * 2), "-c:a", "pcm_s16le", "-ar", "48000", "-ac", "2"]

    def _game_volume(self) -> float:
        return {"keep": 1.0, "reduce": 0.35, "mute": 0.0}[self.s.game_audio]

    # ------------------------------------------------------------------ stage 1: clips
    def _render_clip(self, c: Clip, n_frames: int, out: Path, is_first: bool, is_last: bool, crf: int,
                     progress: Callable[[float], None]) -> None:
        if c.kind == "video":
            args = self._video_clip_args(c, n_frames, is_first, is_last)
        else:
            args = self._still_clip_args(c, n_frames, is_first, is_last)
        run_ffmpeg([*args, *self._encode_args(crf, n_frames), str(out)], on_progress=progress,
                   should_cancel=self.should_cancel)

    def _reframe(self, src_w: int, src_h: int, crop_x: float | None, label_in: str, label_out: str,
                 g: list[str]) -> None:
        W, H = self.frame.w, self.frame.h
        if src_h < LOW_RES_HEIGHT:  # small and usually re-compressed (e.g. sent via WhatsApp): smooth block edges
            g.append(f"[{label_in}]deblock=filter=weak:block=8[{label_in}db]")
            label_in = f"{label_in}db"
        ta = W / H
        sa = src_w / max(src_h, 1)
        mode = self.s.reframe
        if mode == "rotate" and sa > 1 > ta:
            # Velocity-edit look: turn landscape gameplay sideways so it fills the vertical frame, HUD and all.
            g.append(f"[{label_in}]transpose=2,scale={W}:{H}:force_original_aspect_ratio=increase:flags=lanczos,"
                     f"crop={W}:{H}[{label_out}]")
            return
        if abs(sa - ta) / ta < 0.02:
            g.append(f"[{label_in}]scale={W}:{H}:flags=lanczos[{label_out}]")
            return
        if mode == "blur_fill" or (sa < ta and ta / sa > 1.3):
            # Fit the whole frame and fill the empty space with a blurred, darkened copy.
            g.append(f"[{label_in}]split=2[bf_bg][bf_fg]")
            g.append(f"[bf_bg]scale={W // 4}:{H // 4}:force_original_aspect_ratio=increase,crop={W // 4}:{H // 4},"
                     f"gblur=sigma=8,eq=brightness=-0.08:saturation=1.1,scale={W}:{H}[bf_bgb]")
            g.append(f"[bf_fg]scale={W}:{H}:force_original_aspect_ratio=decrease:flags=lanczos[bf_fgs]")
            g.append(f"[bf_bgb][bf_fgs]overlay=(W-w)/2:(H-h)/2[{label_out}]")
            return
        if sa > ta:  # source wider: crop width, following the action horizontally
            cw = int(src_h * ta) // 2 * 2
            cx = 0.5 if (mode == "center_crop" or crop_x is None) else min(max(crop_x, 0.0), 1.0)
            # Pull toward the centre a little so HUD-edge noise doesn't yank the crop.
            cx = 0.5 + (cx - 0.5) * 0.7
            x = int(min(max(cx * src_w - cw / 2, 0), src_w - cw))
            g.append(f"[{label_in}]crop={cw}:{src_h}:{x}:0,scale={W}:{H}:flags=lanczos[{label_out}]")
        else:  # source taller: crop height around the centre
            ch = int(src_w / ta) // 2 * 2
            y = max(0, (src_h - ch) // 2)
            g.append(f"[{label_in}]crop={src_w}:{ch}:0:{y},scale={W}:{H}:flags=lanczos[{label_out}]")

    def _video_clip_args(self, c: Clip, n_frames: int, is_first: bool, is_last: bool) -> list[str]:
        m = self.media[c.media_id]  # type: ignore[index]
        fps = self.spec.fps
        out_dur = n_frames / fps
        src_len = c.end - c.start
        args = ["-ss", f"{c.start:.3f}", "-t", f"{src_len + 0.25:.3f}", "-i", str(m.path)]
        idx = 1
        leak_idx = None
        if self.fx.light_leak(c):
            leak = graphics.light_leak(self.assets / "light_leak.png")
            args += ["-loop", "1", "-framerate", str(fps), "-t", f"{out_dur:.3f}", "-i", str(leak)]
            leak_idx = idx
            idx += 1
        gv = 0.0 if c.muted else (1.0 if c.reaction else self._game_volume())
        has_audio = bool(m.info.get("has_audio")) and gv > 0
        null_idx = None
        if not has_audio:
            args += ["-f", "lavfi", "-t", f"{out_dur:.3f}", "-i", "anullsrc=r=48000:cl=stereo"]
            null_idx = idx

        g: list[str] = []
        # Speed ramp: split into normal / slow / normal parts.
        parts: list[tuple[float, float, float]] = []
        if c.ramp:
            a = min(max(c.ramp.at, 0.0), src_len)
            b = min(a + c.ramp.duration, src_len)
            o = c.ramp.outer
            for s0, s1, sp in ((0.0, a, o), (a, b, c.ramp.speed), (b, src_len, o)):
                if s1 - s0 >= 1.0 / fps:
                    parts.append((s0, s1, sp))
        if len(parts) > 1:
            k = len(parts)
            g.append(f"[0:v]split={k}" + "".join(f"[vp{i}]" for i in range(k)))
            for i, (s0, s1, sp) in enumerate(parts):
                chain = f"[vp{i}]trim=start={f(s0)}:end={f(s1)},setpts=(PTS-STARTPTS)/{f(sp)}"
                chain += f",framerate=fps={fps}" if sp < 1 else f",fps={fps}"
                if sp > 1 and self.s.effects.velocity:
                    chain += ",tmix=frames=3:weights='1 2 1'"  # velocity blur trails on the fast parts
                g.append(chain + f"[vq{i}]")
            g.append("".join(f"[vq{i}]" for i in range(k)) + f"concat=n={k}:v=1:a=0[vr]")
            if has_audio:
                g.append(f"[0:a]asplit={k}" + "".join(f"[ap{i}]" for i in range(k)))
                for i, (s0, s1, sp) in enumerate(parts):
                    tempo = ""
                    if sp < 1:
                        tempo = ",atempo=0.5,atempo=" + f(sp / 0.5) if sp < 0.5 else f",atempo={f(sp)}"
                    elif sp > 1:
                        tempo = f",atempo={f(sp)}"
                    g.append(f"[ap{i}]atrim=start={f(s0)}:end={f(s1)},asetpts=PTS-STARTPTS{tempo}[aq{i}]")
                g.append("".join(f"[aq{i}]" for i in range(k)) + f"concat=n={k}:v=0:a=1[ar]")
        else:
            g.append(f"[0:v]setpts=PTS-STARTPTS,fps={fps}[vr]")
            if has_audio:
                g.append("[0:a]asetpts=PTS-STARTPTS[ar]")

        self._reframe(int(m.info.get("width", self.frame.w)), int(m.info.get("height", self.frame.h)),
                      c.crop_x, "vr", "vf", g)
        grade = [] if c.reaction else self.fx.grade(m.color)
        if grade and self.s.effects.sharpen and int(m.info.get("height", self.frame.h)) < LOW_RES_HEIGHT < self.frame.h:
            grade.append("unsharp=5:5:0.35:5:5:0")  # restore edges softened by upscaling
        cur = "vf"
        if grade:
            g.append(f"[{cur}]" + ",".join(grade) + "[vg]")
            cur = "vg"
        if self.fx.glow() and not c.reaction:
            # Blend in RGB: screen-blending YUV chroma planes shifts every pixel toward magenta.
            # Only the brightest parts (muzzle flashes, fire, explosions) glow; darks stay dark.
            g.append(f"[{cur}]format=gbrp,split=2[gl0][gl1]")
            g.append("[gl1]curves=all='0/0 0.72/0 1/1',gblur=sigma=12[glb]")
            g.append("[gl0][glb]blend=all_mode=screen:all_opacity=0.5,format=yuv420p[vglow]")
            cur = "vglow"
        peak_out = None
        if c.ramp:
            peak_out = c.ramp.at + (c.ramp.duration / c.ramp.speed) / 2
        elif c.shake:
            peak_out = src_len * 0.55
        finish = self.fx.finish(c, out_dur, self.frame, is_first, is_last, peak_out,
                                [c.out_time(h) for h in c.hits])
        if leak_idx is not None:
            g.append(f"[{leak_idx}:v]format=rgba,scale={self.frame.w}:{self.frame.h},"
                     f"fade=t=in:st=0:d=0.12:alpha=1,fade=t=out:st=0.25:d=0.5:alpha=1[lk]")
            g.append(f"[{cur}][lk]overlay=0:0:eof_action=pass[vlk]")
            cur = "vlk"
        iris = is_first and self.s.effects.iris_intro and not c.reaction and out_dur > IRIS_SECONDS + 0.2
        g.append(f"[{cur}]" + ",".join([*finish, "format=yuv420p", "setsar=1"]) + ("[vfin]" if iris else "[vout]"))
        if iris:
            # Scope intro: the picture opens as a circle growing out of black. geq only runs on the first second.
            T = IRIS_SECONDS
            inside = f"lte(hypot((X/W-0.5)*W/H,Y/H-0.5),0.62*pow(min(1,T/{f(T)}),1.6))"
            g.append("[vfin]split=2[ir0][ir1]")
            g.append(f"[ir0]trim=end={f(T)},setpts=PTS-STARTPTS,"
                     f"geq=lum='if({inside},lum(X,Y),16)':cb='if({inside},cb(X,Y),128)':cr='if({inside},cr(X,Y),128)'[ira]")
            g.append(f"[ir1]trim=start={f(T)},setpts=PTS-STARTPTS[irb]")
            g.append("[ira][irb]concat=n=2:v=1:a=0,setsar=1[vout]")
        a_in = "ar" if has_audio else f"{null_idx}:a"
        fade_out = max(0.0, out_dur - 0.03)
        a_chain = (f"[{a_in}]aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo,"
                   f"volume={f(gv if has_audio else 1.0)},afade=t=in:d=0.02,apad,atrim=0:{f(out_dur)},"
                   f"afade=t=out:st={f(fade_out)}:d=0.03[aout]")
        if is_last:
            a_chain = a_chain.replace("[aout]", f",afade=t=out:st={f(max(0.0, out_dur - 0.6))}:d=0.6[aout]")
        g.append(a_chain)
        return [*args, "-filter_complex", ";".join(g), "-map", "[vout]", "-map", "[aout]"]

    def _prepare_still(self, c: Clip) -> Path:
        """Image or card, sized to cover the frame with ~12% headroom for motion."""
        W, H = self.frame.w, self.frame.h
        tw, th = int(W * 1.12) // 2 * 2, int(H * 1.12) // 2 * 2
        out = self.work / f"still_{c.id}.png"
        if c.kind == "card":
            graphics.card_image(tw, th, c.text or self.s.outro_text or "CODM Beast Studio", c.subtitle).save(out)
            return out
        m = self.media[c.media_id]  # type: ignore[index]
        if self.s.effects.auto_enhance and m.source == "upload":
            # Raw screenshots get the same conservative Auto Enhance as Image Studio.
            im, _ = apply_edit(m.path, ImageEdit(auto_enhance=True, max_size=4096))
        else:
            with Image.open(m.path) as im:
                im = ImageOps.exif_transpose(im)
                if getattr(im, "n_frames", 1) > 1:
                    im.seek(0)
                im = im.convert("RGBA")
                bg = Image.new("RGBA", im.size, (11, 11, 18, 255))
                im = Image.alpha_composite(bg, im).convert("RGB")
        ia, ta = im.width / im.height, tw / th
        if abs(ia - ta) / ta > 0.25:
            back = ImageOps.fit(im, (tw // 4, th // 4)).filter(ImageFilter.GaussianBlur(6)).resize((tw, th))
            fg = ImageOps.contain(im, (tw, th), Image.LANCZOS)
            back.paste(fg, ((tw - fg.width) // 2, (th - fg.height) // 2))
            im = back
        else:
            im = ImageOps.fit(im, (tw, th), Image.LANCZOS)
        im.save(out)
        return out

    def _still_clip_args(self, c: Clip, n_frames: int, is_first: bool, is_last: bool) -> list[str]:
        fps = self.spec.fps
        D = n_frames / fps
        still = self._prepare_still(c)
        W, H = self.frame.w, self.frame.h
        args = ["-loop", "1", "-framerate", str(fps), "-t", f"{D + 0.1:.3f}", "-i", str(still),
                "-f", "lavfi", "-t", f"{D:.3f}", "-i", "anullsrc=r=48000:cl=stereo"]
        z0 = 1.01 / 1.12
        motion = c.motion if c.kind == "image" else "zoom_in"
        if motion == "zoom_in":
            mv = [f"scale=w='trunc(iw*({f(z0)}+{f(1 - z0)}*t/{f(D)})/2)*2':h=-2:eval=frame", f"crop={W}:{H}"]
        elif motion == "zoom_out":
            mv = [f"scale=w='trunc(iw*(1-{f(1 - z0)}*t/{f(D)})/2)*2':h=-2:eval=frame", f"crop={W}:{H}"]
        elif motion == "pan_left":
            mv = [f"crop={W}:{H}:x='(iw-ow)*(1-t/{f(D)})':y='(ih-oh)/2'"]
        elif motion == "pan_right":
            mv = [f"crop={W}:{H}:x='(iw-ow)*t/{f(D)}':y='(ih-oh)/2'"]
        else:
            mv = [f"crop={W}:{H}"]
        finish = self.fx.finish(c, D, self.frame, is_first, is_last)
        g = [f"[0:v]format=yuv444p,{','.join(mv)},{','.join([*finish, 'format=yuv420p', 'setsar=1'])}[vout]",
             f"[1:a]aformat=sample_fmts=fltp:channel_layouts=stereo,apad,atrim=0:{f(D)}[aout]"]
        return [*args, "-filter_complex", ";".join(g), "-map", "[vout]", "-map", "[aout]"]

    # ------------------------------------------------------------------ stage 2: overlays + audio
    def _overlays(self, tl: Timeline, total: float) -> list[tuple[Path, Overlay, bool]]:
        """Rasterise overlays to PNGs. Returns (image path, overlay, is_animated_gif)."""
        W, H = self.frame.w, self.frame.h
        short = min(W, H)
        out: list[tuple[Path, Overlay, bool]] = []
        for i, o in enumerate(sorted(tl.overlays, key=lambda o: o.layer)):
            start, end = max(0.0, o.start), min(total, o.end)
            if end - start < 0.05:
                continue
            o = o.model_copy(update={"start": start, "end": end})
            p = self.work / f"ovl_{i:03d}.png"
            if o.type in ("text", "counter"):
                if not o.text.strip():
                    continue
                img = graphics.text_image(o.text, int(short * 0.07 * o.scale), o.color, o.outline,
                                          rotation=o.rotation, opacity=o.opacity,
                                          badge="#0B0B12" if o.type == "counter" else None)
                img.save(p)
                out.append((p, o, False))
            elif o.type == "sticker":
                m = self.media.get(o.media_id or "")
                if not m:
                    continue
                target_w = int(W * 0.25 * o.scale)
                if m.info.get("animated"):
                    out.append((m.path, o, True))
                else:
                    graphics.scaled_overlay(m.path, target_w, o.rotation, o.opacity).save(p)
                    out.append((p, o, False))
        s = self.s
        wm_overlay = None
        if s.watermark_media_id and s.watermark_media_id in self.media:
            img = graphics.scaled_overlay(self.media[s.watermark_media_id].path, int(W * 0.14), 0,
                                          s.watermark_opacity)
            wm_overlay = img
        elif s.watermark_text.strip():
            wm_overlay = graphics.text_image(s.watermark_text, int(short * 0.035), "#FFFFFF", "#000000",
                                             shadow=False, opacity=s.watermark_opacity)
        if wm_overlay is not None:
            p = self.work / "watermark.png"
            wm_overlay.save(p)
            margin = 0.03
            xs = {"top_left": margin, "bottom_left": margin, "top_right": 1 - margin, "bottom_right": 1 - margin}
            ys = {"top_left": margin, "top_right": margin, "bottom_left": 1 - margin, "bottom_right": 1 - margin}
            pos = s.watermark_position
            ow, oh = wm_overlay.size
            cx = xs[pos] + (ow / 2 / W if "left" in pos else -ow / 2 / W)
            cy = ys[pos] + (oh / 2 / H if "top" in pos else -oh / 2 / H)
            out.append((p, Overlay(id="watermark", type="sticker", start=0, end=total, x=cx, y=cy,
                                   animation="none", layer=99), False))
        return out

    @staticmethod
    def _pos_expr(o: Overlay, axis: str, size: int) -> str:
        base = o.x if axis == "x" else o.y
        T = f"(t-{f(o.start)})"
        if o.keyframes:
            kfs = sorted(o.keyframes, key=lambda k: k.t)
            vals = [(k.t, k.x if axis == "x" else k.y) for k in kfs]
            expr = f(vals[-1][1])
            for (t0, v0), (t1, v1) in reversed(list(zip(vals, vals[1:]))):
                span = max(t1 - t0, 1e-3)
                expr = f"if(lt({T},{f(t1)}),{f(v0)}+({f(v1 - v0)})*max(0,{T}-{f(t0)})/{f(span)},{expr})"
            expr = f"if(lt({T},{f(vals[0][0])}),{f(vals[0][1])},{expr})"
        else:
            expr = f(base)
        px = f"{size}*({expr})"
        if axis == "x" and o.animation == "slide_left":
            px += f"+{size}*0.35*pow(max(0,1-{T}/0.35),2)"
        if axis == "y" and o.animation == "slide_up":
            px += f"+{size}*0.08*pow(max(0,1-{T}/0.35),2)"
        if axis == "y" and o.animation == "bounce":
            px += f"-{size}*0.04*abs(sin({T}*7))*exp(-{T}*2.5)"
        return px

    def _final(self, concat_list: Path, clips: list[Clip], bounds: list[float], total: float,
               overlays: list[tuple[Path, Overlay, bool]], tl: Timeline, out_path: Path, copy_video: bool) -> None:
        s = self.s
        fps = self.spec.fps
        W, H = self.frame.w, self.frame.h
        args = ["-f", "concat", "-safe", "0", "-i", str(concat_list)]
        idx = 1
        g: list[str] = []
        a_parts: list[str] = []
        game_audible = s.game_audio != "mute"
        game = "0:a"

        music_label = None
        if tl.music and tl.music.media_id in self.media:
            m = self.media[tl.music.media_id]
            args += ["-stream_loop", "-1", "-ss", f"{tl.music.offset:.3f}", "-i", str(m.path)]
            mi = idx
            idx += 1
            fo = min(tl.music.fade_out, total / 3)
            # A reaction punchline cuts the music dead, like a record scratch, so the clip's own sound lands.
            stop = next((bounds[i] for i, c in enumerate(clips) if c.reaction and i < len(bounds)), None)
            if stop is not None and stop > 0.5:
                fade = f"afade=t=out:st={f(max(0.0, stop - 0.08))}:d=0.08"
            else:
                fade = f"afade=t=out:st={f(max(0.0, total - fo))}:d={f(fo)}"
            g.append(f"[{mi}:a]aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo,"
                     f"atrim=0:{f(total)},asetpts=PTS-STARTPTS,volume={f(tl.music.volume)},"
                     f"afade=t=in:st=0:d={f(min(tl.music.fade_in, total / 3))},{fade}[mus]")
            music_label = "mus"
            if s.ducking and game_audible and s.duck_amount > 0:
                g.append("[0:a]asplit=2[g_main][g_sc]")
                ratio = 2 + 14 * s.duck_amount
                g.append(f"[mus][g_sc]sidechaincompress=threshold=0.02:ratio={f(ratio)}:attack=5:release=350"
                         f":makeup=1[mduck]")
                game, music_label = "g_main", "mduck"
        if game_audible:
            a_parts.append(f"[{game}]")
        elif not music_label:
            a_parts.append(f"[{game}]")  # silent bed keeps the audio track present
        if music_label:
            a_parts.append(f"[{music_label}]")

        if s.transition_sfx:
            events = []
            for c, t in zip(clips[1:], bounds[1:-1]):
                if c.transition in ("flash", "glitch"):
                    events.append((t, "impact"))
                elif c.transition in ("zoom", "whip"):
                    events.append((t, "whoosh"))
            if events:
                sfx = build_sfx_bed(self.assets, events, total, self.work / "sfx.wav")
                args += ["-i", str(sfx)]
                g.append(f"[{idx}:a]aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo,"
                         f"volume=0.8[sfx]")
                a_parts.append("[sfx]")
                idx += 1

        if len(a_parts) > 1:
            g.append("".join(a_parts) + f"amix=inputs={len(a_parts)}:duration=first:normalize=0[amix]")
            a_cur = "amix"
        else:
            a_cur = a_parts[0].strip("[]")
        if s.normalize_audio:
            g.append(f"[{a_cur}]loudnorm=I=-14:TP=-1.5:LRA=11,aresample=48000[aout]")
        else:
            g.append(f"[{a_cur}]alimiter=limit=0.95,aresample=48000[aout]")

        v_cur = "0:v"
        for k, (p, o, animated) in enumerate(overlays):
            if animated:
                args += ["-ignore_loop", "0", "-t", f"{total:.3f}", "-i", str(p)]
            else:
                args += ["-loop", "1", "-framerate", str(fps), "-t", f"{total:.3f}", "-i", str(p)]
            chain = [f"[{idx}:v]format=rgba"]
            if animated:
                tw = int(W * 0.25 * o.scale) // 2 * 2
                chain.append(f"scale={tw}:-2")
                if o.rotation:
                    chain.append(f"rotate={f(math.radians(o.rotation))}:c=none:ow=rotw(iw):oh=roth(ih)")
                if o.opacity < 1:
                    chain.append(f"colorchannelmixer=aa={f(o.opacity)}")
            if o.animation == "pop":
                chain.append(f"scale=w='trunc(iw*min(1,0.55+0.45*max(0,t-{f(o.start)})/0.18)/2)*2':h=-2:eval=frame")
            if o.animation != "none":
                fd = min(0.2, (o.end - o.start) / 4)
                chain.append(f"fade=t=in:st={f(o.start)}:d={f(fd)}:alpha=1")
                chain.append(f"fade=t=out:st={f(o.end - fd)}:d={f(fd)}:alpha=1")
            g.append(",".join(chain) + f"[ov{k}]")
            x = self._pos_expr(o, "x", W) + "-w/2"
            y = self._pos_expr(o, "y", H) + "-h/2"
            nxt = f"vo{k}"
            g.append(f"[{v_cur}][ov{k}]overlay=x='{x}':y='{y}':enable='between(t,{f(o.start)},{f(o.end)})'"
                     f":eof_action=pass[{nxt}]")
            v_cur = nxt
            idx += 1
        if overlays:
            g.append(f"[{v_cur}]format=yuv420p[vout]")
            v_map = "[vout]"
        else:
            v_map = "0:v"
        args += ["-filter_complex", ";".join(g), "-map", v_map, "-map", "[aout]", "-t", f"{total:.6f}"]
        if copy_video:
            args += ["-c:v", "copy", "-movflags", "+faststart"]
        else:
            args += [*self.spec.video_args, "-r", str(fps)]
        args += [*self.spec.audio_args, str(out_path)]
        run_ffmpeg(args, should_cancel=self.should_cancel,
                   on_progress=lambda sec: self.on_progress(0.75 + 0.25 * min(1.0, sec / max(total, 0.1)),
                                                            "Mixing audio and encoding"))

    def cleanup(self) -> None:
        shutil.rmtree(self.work, ignore_errors=True)
