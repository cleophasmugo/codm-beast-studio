"""Application settings, loaded from environment variables (prefix BEAST_) or a .env file."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="BEAST_", env_file=".env", extra="ignore")

    # Storage and database
    data_dir: Path = Path("./data")
    database_url: str = ""  # empty -> SQLite file inside data_dir
    storage_backend: str = "local"  # only "local" ships; see storage/base.py for the S3 interface

    # Jobs. Empty broker URL -> jobs run on a thread pool inside the API process (no Redis needed).
    broker_url: str = ""
    max_parallel_jobs: int = 1
    job_timeout_seconds: int = 3600

    # Auth: when set, every /api request needs `Authorization: Bearer <token>` (or ?access_token=).
    api_token: str = ""
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173", "http://127.0.0.1:5173"])

    # Limits
    max_upload_mb: int = 4096
    max_video_minutes: float = 60.0
    max_audio_minutes: float = 30.0
    max_image_megapixels: float = 50.0
    retention_days: int = 0  # 0 = keep forever

    # FFmpeg
    ffmpeg_bin: str = "ffmpeg"
    ffprobe_bin: str = "ffprobe"
    ffmpeg_threads: int = 0  # 0 = let ffmpeg decide
    x264_preset: str = "veryfast"
    font_file: str = ""

    # Analysis
    analysis_fps: float = 6.0
    detector_plugins: str = ""  # comma-separated "module:Class" entries, see services/detectors.py

    # Frontend build to serve at / (optional)
    frontend_dist: Path = Path(__file__).resolve().parents[3] / "frontend" / "dist"

    @property
    def resolved_data_dir(self) -> Path:
        return self.data_dir.resolve()

    @property
    def sqlalchemy_url(self) -> str:
        if self.database_url:
            return self.database_url
        return f"sqlite:///{self.resolved_data_dir / 'beast.sqlite3'}"

    def dir(self, name: str) -> Path:
        p = self.resolved_data_dir / name
        p.mkdir(parents=True, exist_ok=True)
        return p


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    s.resolved_data_dir.mkdir(parents=True, exist_ok=True)
    return s


FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/Library/Fonts/Arial Bold.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
]


def find_font() -> str | None:
    s = get_settings()
    if s.font_file and Path(s.font_file).exists():
        return s.font_file
    for c in FONT_CANDIDATES:
        if Path(c).exists():
            return c
    return None
