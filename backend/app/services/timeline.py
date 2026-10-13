"""ClipSelector and TimelineBuilder: from ranked candidates to a beat-synced timeline."""

from __future__ import annotations

import itertools
import math
import uuid
from dataclasses import dataclass

from ..presets import PRESETS
from ..schemas import Clip, MusicTrack, Overlay, ProjectSettings, SpeedRamp, Timeline
from .highlights import KILL_LEAD, KILL_TAIL, Candidate

MIN_CLIP = 1.0  # seconds of output; shorter cuts are unreadable


def _id() -> str:
    return uuid.uuid4().hex[:10]


def _kill_times(c: Candidate) -> list[float]:
    return sorted(float(ev["time"]) for ev in c.events if ev.get("label") == "kill")


class ClipSelector:
    """Greedy best-first selection with a variety penalty and no overlapping footage."""

    def __init__(self, variety: float = 0.5, min_relative_score: float = 0.3):
        self.variety = variety
        self.min_relative_score = min_relative_score

    def select(self, candidates: list[Candidate], target_seconds: float | None, est_clip_len: float,
               media_order: list[str]) -> list[Candidate]:
        if not candidates:
            return []
        best = max(c.score for c in candidates)
        pool = [c for c in candidates if c.score >= best * self.min_relative_score]
        chosen: list[Candidate] = []
        auto = target_seconds is None
        budget = target_seconds if target_seconds else 90.0
        total = 0.0
        while pool and total < budget - est_clip_len * 0.5:
            def adjusted(c: Candidate) -> float:
                same = [x for x in chosen if x.media_id == c.media_id]
                near = any(abs(x.peak - c.peak) < 8 for x in same)
                return c.score - self.variety * (0.08 * len(same) + (0.2 if near else 0.0))
            pool.sort(key=adjusted, reverse=True)
            c = pool.pop(0)
            if any(x.media_id == c.media_id and c.start < x.end and x.start < c.end for x in chosen):
                continue
            if auto and c.score < best * 0.45 and len(chosen) >= 3:
                break
            chosen.append(c)
            total += est_clip_len
        order = {m: i for i, m in enumerate(media_order)}
        chosen.sort(key=lambda c: (order.get(c.media_id, 999), c.peak))
        return chosen


@dataclass
class MediaMeta:
    id: str
    kind: str
    duration: float = 0.0


class TimelineBuilder:
    def __init__(self, settings: ProjectSettings):
        self.s = settings
        self.hints = PRESETS.get(settings.preset, PRESETS["beast"])

    def beat_grid(self, music: dict | None, needed: float) -> tuple[list[float], float]:
        """Beat times (relative to montage start) covering at least `needed` seconds."""
        if music and music.get("beats"):
            off = float(music.get("offset", music.get("suggested_offset", 0.0)))
            bpm = float(music.get("bpm") or 120.0)
            grid = [b - off for b in music["beats"] if b >= off - 1e-6]
            if not grid or grid[0] > 0.05:
                grid = [0.0, *grid]
        else:
            bpm = {"cinematic": 90.0, "smooth": 100.0}.get(self.s.preset, 120.0)
            grid = [0.0]
        step = 60.0 / bpm
        while grid[-1] < needed + 30:
            grid.append(grid[-1] + step)
        return grid, bpm

    def build(self, selected: list[Candidate], media: dict[str, MediaMeta], image_ids: list[str],
              music: dict | None = None, hook_first: bool | None = None) -> Timeline:
        s = self.s
        notes: list[str] = []
        clips_c = list(selected)
        hook_first = self.hints.get("hook_first", False) if hook_first is None else hook_first
        if len(clips_c) >= 3 and s.finale_last:
            best = max(clips_c, key=lambda c: c.score)
            clips_c.remove(best)
            if hook_first:
                second = max(clips_c, key=lambda c: c.score)
                clips_c.remove(second)
                clips_c.insert(0, second)
            clips_c.append(best)
        best_score = max((c.score for c in selected), default=0)

        # Interleave screenshot scenes.
        elements: list[tuple[str, object]] = [("video", c) for c in clips_c]
        if image_ids:
            if s.preset == "showcase" or not elements:
                mixed: list[tuple[str, object]] = []
                vids = iter(elements)
                for img in image_ids:
                    mixed.append(("image", img))
                    v = next(vids, None)
                    if v:
                        mixed.append(v)
                mixed.extend(vids)
                elements = mixed
            else:
                gap = max(1, len(elements) // (len(image_ids) + 1))
                for k, img in enumerate(image_ids):
                    pos = min(len(elements), gap * (k + 1) + k)
                    elements.insert(pos, ("image", img))
        if s.outro_text:
            elements.append(("card", s.outro_text))

        target = float(s.target_duration) if s.target_duration else None
        grid, bpm = self.beat_grid(music, max(target or 0, 90.0) * 2)
        beat_len = 60.0 / bpm
        min_beats = max(1, int(-(-MIN_CLIP // beat_len)))
        ranked = sorted(selected, key=lambda c: -c.score)
        top_ids = {id(c) for c in ranked[:max(1, len(ranked) // 4)]}

        # Plan beats per element, then grow clips into their surrounding action if we're short of target.
        plan: list[list] = []
        for kind, item in elements:
            if kind == "video":
                c = item  # type: ignore[assignment]
                n = max(min_beats, s.beats_per_clip * (2 if id(c) in top_ids and s.effects.speed_ramps else 1))
                kills = _kill_times(c)
                if kills:  # enough beats to show the whole fight and every kill (slow-mo eats ~20% of source)
                    need = min(kills[-1] - kills[0] + KILL_LEAD + KILL_TAIL, c.end - c.start) / 0.8
                    n = max(n, math.ceil(need / beat_len))
            elif kind == "image":
                n = max(min_beats, round(s.image_duration / beat_len))
            else:
                n = max(min_beats, round(3.0 / beat_len))
            plan.append([kind, item, n])
        if target:
            total_beats = sum(p[2] for p in plan)
            growable = [p for p in plan if p[0] == "video"]
            changed = True
            while growable and total_beats * beat_len < target - beat_len * 0.5 and changed:
                changed = False
                for p in growable:
                    c = p[1]
                    if (p[2] + 1) * beat_len <= (c.end - c.start) + beat_len * 0.5:
                        p[2] += 1
                        total_beats += 1
                        changed = True
                        if total_beats * beat_len >= target - beat_len * 0.5:
                            break

        pool = self.hints.get("transitions", ["cut"])
        trans_cycle = itertools.cycle(pool)
        clips: list[Clip] = []
        bi = 0
        for kind, item, n in plan:
            if target and grid[bi] >= target - 0.25 and kind != "card":
                continue
            if bi + n >= len(grid):
                break
            transition = s.transition if s.transition != "auto" else next(trans_cycle)
            if not clips and transition in ("whip", "glitch"):
                transition = "cut"
            if kind == "video":
                c: Candidate = item  # type: ignore[assignment]
                meta = media.get(c.media_id)
                if not meta:
                    continue
                is_top = id(c) in top_ids
                if target:
                    while n > min_beats and grid[bi + n] > target + beat_len * 0.5:
                        n -= 1
                out = grid[bi + n] - grid[bi]
                ramp = None
                src_len = out
                if is_top and s.effects.speed_ramps and out >= 1.6:
                    slow_out = min(out * 0.4, 2.0)
                    speed = 0.5
                    rd = slow_out * speed
                    src_len = out - slow_out + rd
                    ramp = SpeedRamp(at=0.0, duration=round(rd, 3), speed=speed)
                if src_len > meta.duration:
                    src_len = meta.duration
                    ramp = None
                    notes.append("A clip was shorter than its beat slot; it plays in full.")
                kills = _kill_times(c)
                if kills:
                    # End just after the last kill notice, so the clip lands on the payoff, never before it.
                    start = kills[-1] + KILL_TAIL - src_len
                else:
                    # Centre the window on the peak, but stay inside the candidate's context where possible.
                    start = c.peak - src_len * 0.55
                    start = min(start, max(c.start, c.end - src_len)) if src_len <= c.end - c.start else start
                    start = max(start, min(c.start, c.peak - src_len * 0.3))
                start = min(max(0.0, start), max(0.0, meta.duration - src_len))
                if ramp:
                    ramp.at = round(min(max(0.0, c.peak - start - ramp.duration / 2), src_len - ramp.duration), 3)
                clips.append(Clip(
                    id=_id(), kind="video", media_id=c.media_id, start=round(start, 3),
                    end=round(start + src_len, 3), ramp=ramp, transition=transition,
                    punch_in=s.effects.punch_in and c.score >= best_score * 0.6,
                    shake=s.effects.shake and is_top, crop_x=c.crop_x, score=round(c.score, 4),
                    reasons=c.reasons,
                ))
            elif kind == "image":
                motions = ["zoom_in", "pan_right", "zoom_out", "pan_left"]
                clips.append(Clip(id=_id(), kind="image", media_id=str(item), duration=round(grid[bi + n] - grid[bi], 3),
                                  transition=transition, motion=motions[len(clips) % 4]))
            else:
                clips.append(Clip(id=_id(), kind="card", text=str(item), subtitle=s.subtitle if not s.title else "",
                                  duration=round(grid[bi + n] - grid[bi], 3), transition="fade"))
            bi += n

        tl = Timeline(clips=clips, bpm=round(bpm, 2), notes=notes)
        if s.music_id:
            m = music or {}
            tl.music = MusicTrack(media_id=s.music_id, offset=float(m.get("offset", m.get("suggested_offset", 0.0))),
                                  volume=s.music_volume)
        tl.overlays = self.default_overlays(tl)
        total = tl.duration()
        if target and total < target - 2 and selected:
            notes.append(f"Only found enough strong action for {total:.0f}s, so the montage is shorter than the "
                         f"{target:.0f}s target instead of being padded with quiet footage.")
        if not selected and not image_ids:
            notes.append("No highlight candidates were found in this footage.")
        tl.notes = notes
        return tl

    def default_overlays(self, tl: Timeline) -> list[Overlay]:
        s = self.s
        out: list[Overlay] = []
        if s.title:
            out.append(Overlay(id=_id(), type="text", text=s.title, start=0.15, end=2.8, x=0.5, y=0.42,
                               scale=1.6, animation="pop", layer=10))
            if s.subtitle:
                out.append(Overlay(id=_id(), type="text", text=s.subtitle, start=0.4, end=2.8, x=0.5, y=0.56,
                                   scale=0.8, animation="slide_up", color="#22D3EE", layer=11))
        if s.clip_counter:
            t = 0.0
            n = 0
            for c in tl.clips:
                d = c.output_duration()
                if c.kind == "video":
                    n += 1
                    out.append(Overlay(id=_id(), type="counter", text=f"HIGHLIGHT {n}", start=round(t, 3),
                                       end=round(t + min(d, 2.0), 3), x=0.14, y=0.1, scale=0.7,
                                       animation="slide_left", color="#A3E635", layer=5))
                t += d
        return out
