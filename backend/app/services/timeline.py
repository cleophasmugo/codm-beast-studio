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
VELOCITY_SLOW, VELOCITY_FAST = 0.4, 1.6  # velocity edit speeds: slow-mo on the action, fast around it
CALLOUTS = {1: "KILL!", 2: "DOUBLE KILL!", 3: "TRIPLE KILL!", 4: "QUAD KILL!", 5: "RAMPAGE!"}


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
                if kills:  # enough beats to show the whole fight and every kill
                    need_src = min(kills[-1] - kills[0] + KILL_LEAD + KILL_TAIL, c.end - c.start)
                    # velocity races through source at 1.6x (plus ~1 s of slow-mo); a plain ramp eats ~20%
                    need = need_src / VELOCITY_FAST + 1.0 if s.effects.velocity else need_src / 0.8
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

            # Over budget (long kill clips): drop the weakest clips rather than chopping kills out of the rest.
            vids = [p for p in plan if p[0] == "video"]
            while len(vids) > 1 and sum(p[2] for p in plan) * beat_len > target + beat_len:
                keep_last = s.finale_last and len(vids) >= 2
                drop = min(vids[:-1] if keep_last else vids, key=lambda p: p[1].score)
                plan.remove(drop)
                vids.remove(drop)

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
                if target and not _kill_times(c):  # never cut a kill short to hit the target length
                    while n > min_beats and grid[bi + n] > target + beat_len * 0.5:
                        n -= 1
                out = grid[bi + n] - grid[bi]
                ramp = None
                src_len = out
                if s.effects.velocity and out >= 1.2:
                    # Velocity edit: race in fast, drop into slow-mo on the action, race out again.
                    slow_out = min(out * 0.45, 2.0)
                    speed, outer = VELOCITY_SLOW, VELOCITY_FAST
                    rd = slow_out * speed
                    src_len = (out - slow_out) * outer + rd
                    ramp = SpeedRamp(at=0.0, duration=round(rd, 3), speed=speed, outer=outer)
                elif is_top and s.effects.speed_ramps and out >= 1.6:
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
                    taken = [cl for cl in clips if cl.kind == "video" and cl.media_id == c.media_id]
                    for cl in taken:  # never replay footage another clip already shows
                        if cl.start < kills[-1] and cl.end > start and cl.end <= kills[0]:
                            start = cl.end
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
                    hits=[round(k, 3) for k in kills if start <= k <= start + src_len],
                ))
            elif kind == "image":
                motions = ["zoom_in", "pan_right", "zoom_out", "pan_left"]
                clips.append(Clip(id=_id(), kind="image", media_id=str(item), duration=round(grid[bi + n] - grid[bi], 3),
                                  transition=transition, motion=motions[len(clips) % 4]))
            else:
                clips.append(Clip(id=_id(), kind="card", text=str(item), subtitle=s.subtitle if not s.title else "",
                                  duration=round(grid[bi + n] - grid[bi], 3), transition="fade"))
            bi += n

        reaction = media.get(s.reaction_clip_id or "")
        if reaction and reaction.duration > 0:
            # The punchline: a hard cut to the user's own meme/facecam clip, before any outro card.
            at = next((i for i, cl in enumerate(clips) if cl.kind == "card"), len(clips))
            clips.insert(at, Clip(id=_id(), kind="video", media_id=reaction.id, start=0.0,
                                  end=round(min(reaction.duration, s.reaction_seconds), 3),
                                  transition="cut", crop_x=0.5, reaction=True, reasons=["reaction ending"]))
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
        if s.kill_callouts:
            out += self.kill_overlays(tl)
        return out

    def kill_overlays(self, tl: Timeline) -> list[Overlay]:
        """KILL! / DOUBLE KILL! pop-ups on each detected kill, and a running kill counter badge."""
        vertical = self.s.aspect in ("9:16", "4:5")
        call_y, badge_x, badge_y = (0.17, 0.5, 0.86) if vertical else (0.24, 0.88, 0.1)
        times: list[tuple[float, int]] = []  # (output time, kill number within its clip)
        t = 0.0
        for c in tl.clips:
            for i, h in enumerate(sorted(c.hits), 1):
                times.append((t + c.out_time(h), i))
            t += c.output_duration()
        out: list[Overlay] = []
        for n, (at, streak) in enumerate(times, 1):
            out.append(Overlay(id=_id(), type="text", text=CALLOUTS.get(streak, f"{streak}X KILL!"),
                               start=round(at, 3), end=round(min(at + 1.1, t), 3), x=0.5, y=call_y,
                               scale=(1.25 if streak > 1 else 1.45) if vertical else (2.2 if streak > 1 else 1.8),
                               color="#FACC15" if streak == 1 else "#F43F5E",
                               outline="#000000", animation="pop", layer=20))
            nxt = times[n][0] if n < len(times) else t
            out.append(Overlay(id=_id(), type="counter", text=f"KILLS {n}", start=round(at, 3),
                               end=round(max(at + 0.5, nxt), 3), x=badge_x, y=badge_y, scale=0.9,
                               color="#A3E635", animation="pop", layer=19))
        return out
