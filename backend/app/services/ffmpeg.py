"""Safe FFmpeg/FFprobe subprocess helpers.

Commands are always argument lists (never a shell string), so user text can't inject
shell syntax. Text drawn on video goes through files (drawtext textfile=) rather than
being spliced into filter strings.
"""

from __future__ import annotations

import json
import logging
import subprocess
import threading
import time
from collections.abc import Callable, Sequence
from functools import lru_cache
from pathlib import Path

from ..core.config import get_settings

log = logging.getLogger(__name__)


class FFmpegError(RuntimeError):
    pass


class Cancelled(RuntimeError):
    pass


ProgressFn = Callable[[float], None]  # receives seconds of output written
CancelFn = Callable[[], bool]


def ffmpeg_bin() -> str:
    return get_settings().ffmpeg_bin


def ffprobe_bin() -> str:
    return get_settings().ffprobe_bin


def run_ffmpeg(args: Sequence[str], *, on_progress: ProgressFn | None = None,
               should_cancel: CancelFn | None = None, timeout: float | None = None) -> None:
    """Run ffmpeg with `args` (without the binary). Raises FFmpegError / Cancelled."""
    threads = get_settings().ffmpeg_threads
    cmd = [ffmpeg_bin(), "-hide_banner", "-nostdin", "-y", "-loglevel", "error",
           "-progress", "pipe:1", "-nostats"]
    if threads:
        cmd += ["-threads", str(threads)]
    cmd += [str(a) for a in args]
    log.debug("ffmpeg %s", " ".join(cmd))
    timeout = timeout or get_settings().job_timeout_seconds
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1)
    stderr_chunks: list[str] = []

    def _drain() -> None:
        assert proc.stderr is not None
        for line in proc.stderr:
            stderr_chunks.append(line)
            if len(stderr_chunks) > 400:
                del stderr_chunks[:200]

    t = threading.Thread(target=_drain, daemon=True)
    t.start()
    started = time.monotonic()
    cancelled = False
    last_check = 0.0
    assert proc.stdout is not None
    for line in proc.stdout:
        line = line.strip()
        if on_progress and line.startswith("out_time_us="):
            try:
                us = int(line.split("=", 1)[1])
                if us >= 0:
                    on_progress(us / 1_000_000)
            except ValueError:
                pass
        now = time.monotonic()
        if now - last_check > 0.5:
            last_check = now
            if should_cancel and should_cancel():
                cancelled = True
                proc.kill()
                break
            if now - started > timeout:
                proc.kill()
                raise FFmpegError(f"FFmpeg exceeded the {timeout:.0f}s time limit")
    proc.wait()
    t.join(timeout=2)
    if cancelled:
        raise Cancelled("Job cancelled")
    if proc.returncode != 0:
        err = "".join(stderr_chunks[-30:]).strip()
        raise FFmpegError(err or f"ffmpeg exited with code {proc.returncode}")


def run_ffmpeg_simple(args: Sequence[str], timeout: float = 600) -> None:
    run_ffmpeg(args, timeout=timeout)


def ffprobe_json(path: Path) -> dict:
    cmd = [ffprobe_bin(), "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=60, check=True)
    except subprocess.CalledProcessError as e:
        raise FFmpegError((e.stderr or "").strip() or "ffprobe could not read this file") from e
    except subprocess.TimeoutExpired as e:
        raise FFmpegError("ffprobe timed out") from e
    return json.loads(out.stdout or "{}")


@lru_cache
def available_encoders() -> set[str]:
    try:
        out = subprocess.run([ffmpeg_bin(), "-hide_banner", "-encoders"], capture_output=True, text=True,
                             timeout=30).stdout
    except (OSError, subprocess.TimeoutExpired):
        return set()
    names = set()
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 2 and len(parts[0]) == 6:
            names.add(parts[1])
    return names


@lru_cache
def ffmpeg_version() -> str:
    try:
        out = subprocess.run([ffmpeg_bin(), "-version"], capture_output=True, text=True, timeout=30).stdout
        return out.splitlines()[0] if out else "unknown"
    except (OSError, subprocess.TimeoutExpired):
        return "not installed"


def escape_filter_path(p: Path | str) -> str:
    """Escape a path for use as a filter option value (e.g. drawtext fontfile/textfile)."""
    s = str(p).replace("\\", "/")
    for ch in ("\\", ":", "'", ",", "[", "]", ";", "="):
        s = s.replace(ch, "\\" + ch)
    return s
