"""Auto-edit presets. Each one is a bundle of ProjectSettings defaults plus editing hints."""

from __future__ import annotations

from typing import Any

from .schemas import ProjectSettings

PRESETS: dict[str, dict[str, Any]] = {
    "beast": {
        "label": "Beast Mode",
        "description": "Hard-hitting 2-beat cuts, flashes, punch-ins and slow-mo on the best moments.",
        "settings": {
            "aspect": "16:9", "target_duration": 30, "look": "beast", "beats_per_clip": 2,
            "effects": {"vignette": True, "glow": True, "speed_ramps": True, "punch_in": True, "shake": True,
                        "flash": True, "chromatic": True, "impact": True},
            "game_audio": "reduce", "kill_callouts": True,
        },
        "transitions": ["flash", "zoom", "cut", "glitch", "flash", "whip"],
        "hook_first": True,
    },
    "cinematic": {
        "label": "Cinematic",
        "description": "Longer shots, fades, letterbox bars, filmic grade and slow-motion ramps.",
        "settings": {
            "aspect": "16:9", "target_duration": 60, "look": "cinematic", "beats_per_clip": 4,
            "effects": {"vignette": True, "speed_ramps": True, "letterbox": True, "motion_blur": True,
                        "light_leaks": True},
            "game_audio": "reduce",
        },
        "transitions": ["fade", "fade", "cut"],
        "hook_first": False,
    },
    "esports": {
        "label": "Competitive Esports",
        "description": "Clean, sharp and readable. Fast cuts without effects that hide gameplay.",
        "settings": {
            "aspect": "16:9", "target_duration": 30, "look": "esports", "beats_per_clip": 2,
            "effects": {"flash": True}, "game_audio": "keep", "clip_counter": True,
        },
        "transitions": ["cut", "cut", "flash"],
        "hook_first": True,
    },
    "smooth": {
        "label": "Smooth and Clean",
        "description": "Gentle fades, natural colour, no aggressive effects.",
        "settings": {
            "aspect": "16:9", "target_duration": 60, "look": "clean", "beats_per_clip": 4,
            "effects": {}, "game_audio": "reduce",
        },
        "transitions": ["fade", "cut"],
        "hook_first": False,
    },
    "neon": {
        "label": "Neon Montage",
        "description": "Violet/cyan grade, glow, light leaks and RGB split hits. 4:5 for feeds.",
        "settings": {
            "aspect": "4:5", "target_duration": 30, "look": "neon", "beats_per_clip": 2,
            "effects": {"glow": True, "light_leaks": True, "chromatic": True, "vignette": True, "flash": True,
                        "punch_in": True, "impact": True},
            "game_audio": "reduce", "kill_callouts": True,
        },
        "transitions": ["glitch", "flash", "zoom", "cut"],
        "hook_first": True,
    },
    "tiktok": {
        "label": "TikTok Vertical",
        "description": "9:16 with motion-following crop, a hook first and punchy beat cuts.",
        "settings": {
            "aspect": "9:16", "target_duration": 30, "look": "beast", "beats_per_clip": 2,
            "reframe": "smart_crop",
            "effects": {"punch_in": True, "flash": True, "speed_ramps": True, "shake": True, "impact": True},
            "game_audio": "reduce", "kill_callouts": True,
        },
        "transitions": ["flash", "zoom", "cut", "whip"],
        "hook_first": True,
    },
    "youtube": {
        "label": "YouTube Gaming",
        "description": "Landscape 16:9, longer runtime, title and outro, balanced effects.",
        "settings": {
            "aspect": "16:9", "target_duration": 120, "look": "esports", "beats_per_clip": 4,
            "effects": {"flash": True, "vignette": True}, "game_audio": "keep",
        },
        "transitions": ["cut", "flash", "fade", "cut"],
        "hook_first": True,
    },
    "shorts": {
        "label": "Shorts / Reels",
        "description": "9:16, 15–30 seconds, blurred-background reframe so the whole HUD stays visible.",
        "settings": {
            "aspect": "9:16", "target_duration": 20, "look": "beast", "beats_per_clip": 2,
            "reframe": "blur_fill",
            "effects": {"punch_in": True, "flash": True, "impact": True}, "game_audio": "reduce",
            "kill_callouts": True,
        },
        "transitions": ["flash", "cut", "zoom"],
        "hook_first": True,
    },
    "showcase": {
        "label": "Screenshot Showcase",
        "description": "Your enhanced screenshots as moving scenes, with short gameplay hits between.",
        "settings": {
            "aspect": "16:9", "target_duration": 30, "look": "clean", "beats_per_clip": 4,
            "image_duration": 3.0, "effects": {"light_leaks": True, "vignette": True},
            "game_audio": "mute",
        },
        "transitions": ["fade", "flash", "zoom"],
        "hook_first": False,
    },
    "streamer": {
        "label": "Streamer TikTok",
        "description": "Crazy vertical edit: whole HUD in a stacked layout, KILL! pop-ups, kill counter, impact "
                       "shake on every kill, and your own reaction clip as the punchline.",
        "settings": {
            "aspect": "9:16", "target_duration": 20, "look": "beast", "beats_per_clip": 2,
            "reframe": "blur_fill",
            "effects": {"punch_in": True, "flash": True, "speed_ramps": True, "shake": True, "impact": True,
                        "glow": True, "chromatic": True},
            "game_audio": "keep", "kill_callouts": True,
        },
        "transitions": ["flash", "glitch", "zoom", "whip", "cut"],
        "hook_first": True,
    },
}


def preset_settings(name: str, base: ProjectSettings | None = None, **overrides: Any) -> ProjectSettings:
    """Settings for a preset; explicit overrides win."""
    p = PRESETS.get(name, PRESETS["beast"])
    data = ProjectSettings().model_dump()
    data["preset"] = name if name in PRESETS else "beast"
    eff = data["effects"]
    for k in ("vignette", "glow", "motion_blur", "speed_ramps", "punch_in", "shake", "flash",
              "light_leaks", "chromatic", "letterbox", "impact"):
        eff[k] = False
    for k, v in p["settings"].items():
        if k == "effects":
            eff.update(v)
        else:
            data[k] = v
    if base is not None:  # keep the user's non-style choices (music, titles, export settings)
        b = base.model_dump()
        for k in ("music_id", "music_volume", "title", "subtitle", "outro_text", "watermark_text",
                  "watermark_media_id", "watermark_position", "watermark_opacity", "resolution", "fps",
                  "quality", "format", "transition_sfx", "normalize_audio", "ducking", "duck_amount",
                  "reaction_clip_id", "reaction_seconds"):
            data[k] = b[k]
    data.update({k: v for k, v in overrides.items() if v is not None})
    return ProjectSettings.model_validate(data)


def preset_list() -> list[dict[str, Any]]:
    return [{"id": k, "label": v["label"], "description": v["description"],
             "aspect": v["settings"].get("aspect", "16:9"),
             "target_duration": v["settings"].get("target_duration")} for k, v in PRESETS.items()]
