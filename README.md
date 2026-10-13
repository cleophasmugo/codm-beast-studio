# CODM Beast Studio

An automatic montage editor for Call of Duty: Mobile gameplay. Upload raw recordings and
screenshots, click **Create My Montage**, and get back a beat-synced, colour-graded, finished
video you can preview and download. No timeline work needed, though there is an optional editor
when you want control.

**Upload → analyse → auto-edit → preview → export.**

| | |
|---|---|
| Frontend | React 19, TypeScript, Vite, Tailwind CSS, Framer Motion, Lucide icons, Vitest |
| Backend | Python 3.13, FastAPI, Pydantic, SQLAlchemy + Alembic |
| Video | FFmpeg / FFprobe (real filters, not CSS previews) |
| Analysis | OpenCV (motion, optical flow, scene changes, exposure), librosa (beats, transients, silence) |
| Jobs | Celery + Redis (or an in-process thread pool for local runs) |
| Database | PostgreSQL (Docker) or SQLite (local) |
| Deploy | Docker + Docker Compose |

---

## Quick start (Docker, recommended)

You need Docker Desktop (Windows/macOS) or Docker Engine + Compose (Linux).

```bash
git clone https://github.com/cleophasmugo/codm-beast-studio.git
cd codm-beast-studio
docker compose up --build
```

When the log shows `Uvicorn running on http://0.0.0.0:8000`, open **http://localhost:8000**.
The first build takes a few minutes; the first start also generates the built-in music
library (about 20 seconds). Later starts take seconds: `docker compose up`.

This starts four containers: `web` (API + UI), `worker` (Celery renders), `db` (PostgreSQL) and
`redis`. Uploads and renders live in the `beastdata` volume. Stop with `Ctrl+C`;
`docker compose down -v` also deletes all data.

To change settings, copy `.env.example` to `.env` and edit it before starting.

## Local development (no Docker)

Requirements: Python 3.12+, Node 22+, FFmpeg 6+ on your PATH.

```bash
# backend
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r backend/requirements-dev.txt
cd backend
uvicorn app.main:app --reload --port 8000
```

With no extra configuration the backend uses SQLite in `backend/data/` and runs jobs on a
background thread, so Redis and PostgreSQL are optional for development.

```bash
# frontend (second terminal)
cd frontend
npm ci
npm run dev                          # http://localhost:5173, proxies /api to :8000
```

Or build the UI once (`npm run build`) and the backend serves it at http://localhost:8000.

To use Celery and PostgreSQL locally, set `BEAST_BROKER_URL=redis://localhost:6379/0` and
`BEAST_DATABASE_URL=postgresql+psycopg://user:pass@localhost:5432/beast`, then also run
`celery -A app.jobs.celery_app worker --beat` from `backend/`.

### Sample media

`python scripts/make_sample_media.py samples` creates safe synthetic test media: a 40-second
"gameplay" video with three action bursts (fast camera moves, muzzle flashes, gunfire-like
audio), a dim screenshot and a transparent sticker. Nothing is taken from the game.

## Using it

1. **Dashboard**: drop your recordings, screenshots, music and PNG stickers on the upload zone.
2. Pick a preset and length, then press **Create My Montage**. Progress, stage and an ETA
   show while it analyses and renders; you can cancel, and retry failed jobs.
3. Watch the result in the player and **Download** the MP4.

Optional extras:

- **Auto Edit**: choose videos, preset, length (15/30/60/120 s or Auto), aspect, music, game
  audio level, title and outro before running.
- **Image Studio**: crop, rotate, aspect presets, colour, looks, vignette, background blur,
  frames, text and sticker layers, before/after view, **Auto Enhance Image**, export PNG/JPEG,
  and **Add to Montage** (the screenshot becomes a moving scene timed to the beat).
- **Music and Audio**: library tracks or your own, volume, game audio keep/reduce/mute,
  ducking, loudness normalisation, transition sound effects.
- **Browse music online** (on the Music and Audio page): search free Jamendo tracks through
  Openverse (no API key needed), preview them and add one to your music in a click. Only tracks
  whose licence allows use in videos are shown (CC0, CC BY, CC BY-SA). The credit line is saved
  as the track's licence; put it in your video description.
- **Effects and Filters**: every effect can be switched off individually; manual colour
  overrides; a before/after frame rendered by the real FFmpeg filter chain.
- **My Projects**: the optional editor. Highlights list with the reason each was picked, clip
  trimming/reordering/removal, transitions, overlays, music offset, undo/redo, revision history,
  preview render and export settings.
- **Export History** and **Settings** (access token, limits, cleanup).

### Presets

| Preset | Aspect | Default length | Style |
|---|---|---|---|
| Beast Mode | 16:9 | 30 s | 2-beat cuts, flashes, punch-ins, shake, slow-mo ramps, glow |
| Cinematic | 16:9 | 60 s | 4-beat shots, fades, letterbox, filmic grade, light leaks, motion blur |
| Competitive Esports | 16:9 | 30 s | clean and sharp, highlight counter, effects that never hide the HUD |
| Smooth and Clean | 16:9 | 60 s | gentle fades, natural colour |
| Neon Montage | 4:5 | 30 s | violet/cyan grade, glow, RGB-split hits, light leaks |
| TikTok Vertical | 9:16 | 30 s | motion-following crop, hook first, punchy cuts |
| YouTube Gaming | 16:9 | 120 s | longer, balanced, title and outro |
| Shorts / Reels | 9:16 | 20 s | blurred-background reframe keeps the whole HUD visible |
| Screenshot Showcase | 16:9 | 30 s | screenshots as moving scenes with gameplay hits between |

Exports: MP4 (H.264/AAC, default), MP4 (H.265) and WebM (VP9/Opus) when your FFmpeg has the
encoders; 16:9, 9:16, 1:1, 4:5; source, 720p, 1080p, 1440p or 2160p; 24 to 60 fps; draft,
standard or high quality.

## How the auto-edit works

1. **MediaInspector** reads duration, size, fps, codecs and audio with FFprobe and validates uploads.
2. **SceneDetector** and the frame sampler decode about 6 frames per second and measure motion,
   optical flow, the horizontal centre of motion, exposure, contrast, saturation, sharpness,
   noise and colour-histogram changes (OpenCV).
3. **AudioAnalyzer** measures loudness, onset strength and high-frequency transients (bursts of
   gunfire-like spikes), and silence. For music it finds tempo, beats, downbeats and the drop.
4. **HighlightAnalyzer** combines those signals with configurable weights into an excitement
   curve, finds peaks, splits long fights into several distinct hits, adds context so a clip
   includes its build-up and never opens with a sliver of the previous scene, and scores
   excitement and clarity. Calm stretches are reported as quiet sections.
5. **ClipSelector** picks the best non-overlapping moments with a variety penalty, stops at the
   target length, and never pads with boring footage (the result tells you if it came out short).
6. **TimelineBuilder** orders the clips (hook first, best moment last), snaps every cut to a
   beat, adds slow-motion ramps on the top moments, spreads screenshots through the montage
   and adds titles, counters and outro cards.
7. **AutoColorCorrector** picks conservative exposure, contrast, saturation, denoise and
   sharpening per video from the measurements (all clamped to avoid clipping or oversaturation).
8. **EffectsComposer** turns preset, look and toggles into FFmpeg filters; **FFmpegRenderer**
   renders each clip, joins them losslessly, then adds overlays, music with ducking under game
   sound, transition sound effects and loudness normalisation (-14 LUFS) in one final encode.
9. **ExportManager** handles formats, sizes and encoder settings; **ThumbnailGenerator** makes
   posters, contact sheets and waveforms.

### Honest limits

- **No kill or headshot recognition out of the box.** Highlights come from motion, loudness,
  sound spikes, flashes and scene changes, and the app always labels them as heuristic. A
  trained model can be plugged in: see `docs/examples/kill_feed_detector.py` and
  `BEAST_DETECTOR_PLUGINS`. Its events are labelled with the model name and confidence.
- With little action in the footage, the montage is shorter than the target rather than
  padded with quiet footage.
- Overlay keyframes animate position only. Opacity, scale and rotation are set per overlay, plus
  fade/pop/slide/bounce entrance animations; per-frame rotation and scale keyframes are not implemented.
- `previews/` before/after frames use unguessable random names but aren't owner-scoped.
- Only local file storage ships. `app/storage/base.py` defines the interface an
  S3-compatible backend would implement.

## Configuration

All settings are environment variables with the `BEAST_` prefix (see `.env.example`):

| Variable | Default | Meaning |
|---|---|---|
| `BEAST_API_TOKEN` | empty | When set, every `/api` request needs `Authorization: Bearer <token>` |
| `BEAST_DATABASE_URL` | SQLite in data dir | e.g. `postgresql+psycopg://user:pass@host/db` |
| `BEAST_BROKER_URL` | empty | Redis URL for Celery; empty runs jobs in-process |
| `BEAST_DATA_DIR` | `./data` | Uploads, renders, thumbnails, SQLite |
| `BEAST_MAX_UPLOAD_MB` | 4096 | Per-file upload limit |
| `BEAST_MAX_VIDEO_MINUTES` / `BEAST_MAX_AUDIO_MINUTES` | 60 / 30 | Duration limits |
| `BEAST_RETENTION_DAYS` | 0 | Delete uploads/exports older than this (0 = never) |
| `BEAST_JOB_TIMEOUT_SECONDS` | 3600 | Hard limit per FFmpeg run |
| `BEAST_MAX_PARALLEL_JOBS` | 1 | Thread-mode concurrency (Celery: `BEAST_WORKER_CONCURRENCY`) |
| `BEAST_X264_PRESET` | veryfast | Speed/size trade-off for H.264 exports |
| `BEAST_DETECTOR_PLUGINS` | empty | `module:Class` list of trained event detectors |
| `BEAST_ONLINE_MUSIC_API` | Openverse | Online music search API base URL; empty turns the feature off |

## API

Interactive docs are at **http://localhost:8000/docs** (OpenAPI JSON at `/openapi.json`,
also saved in `docs/openapi.json`). Main endpoints:

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/media` | Upload files (multipart `files`) |
| GET/PATCH/DELETE | `/api/media/{id}` | Inspect, rename/move to folder, delete |
| GET | `/api/media/{id}/file`, `/thumb`, `/contact-sheet`, `/frame?t=` | Stream (Range), thumbnails, frame grab |
| POST | `/api/montage/quick` | One click: project + auto-edit + render |
| POST/GET/PATCH/DELETE | `/api/projects[/{id}]` | Projects and their settings |
| POST | `/api/projects/{id}/auto-edit` | Analyse, build timeline, render |
| POST | `/api/projects/{id}/render` | Render (`{"preview": true}` for a fast 540p preview) |
| PUT | `/api/projects/{id}/timeline` | Save a manual edit (validated) |
| GET/POST | `/api/projects/{id}/revisions[/{rid}/restore]` | Edit history |
| GET | `/api/projects/{id}/highlights` | Candidates, reasons, evidence, scene cuts, quiet sections |
| POST | `/api/projects/{id}/compare` | Real before/after frames |
| GET/POST | `/api/jobs/{id}`, `/cancel`, `/retry` | Progress, ETA, cancel, retry |
| GET/DELETE | `/api/exports[/{id}]`, `/file`, `/download` | Export history, preview, download |
| POST | `/api/images/{id}/preview`, `/render`, `/analyze` | Image Studio |
| POST | `/api/images/add-to-montage` | Screenshot as a montage scene |
| GET | `/api/system`, `/api/presets`, `/api/health` | Capabilities, presets, health |

## Tests

```bash
cd backend && python -m pytest -q          # unit tests, real FFmpeg renders, full API flow
cd frontend && npm test && npm run typecheck && npm run build
python scripts/make_sample_media.py samples && python frontend/e2e/smoke.py   # browser e2e run against a live server
```

The backend suite generates the synthetic sample media, renders several preset styles and export formats, checks the
results with FFprobe, runs the one-click montage and the screenshot-to-montage flow through the
API, and checks that the Alembic migration matches the models.

## Security and privacy

- Gameplay recordings can contain personal information (usernames, voice chat, notifications).
  Files stay on the server that runs this app until you delete them or the retention period
  ends. Nothing is sent to third parties.
- Runs as a single user by default. **Set `BEAST_API_TOKEN` before exposing it to a network**,
  and put it behind HTTPS. Every table has an `owner_id`, and `app/core/security.py` is the
  one place to swap in real user accounts.
- Uploads are validated by extension and by actually decoding them, with size, duration and
  megapixel limits. Files are stored under random names; the API never returns filesystem paths.
- FFmpeg always runs as an argument list (no shell). User text is rendered with Pillow, never
  inserted into filter strings. Storage keys are checked against path traversal.
- Each job has its own temporary directory, removed when it ends; renders can be cancelled and
  have a time limit. The container runs as a non-root user.

## Project layout

```
backend/
  app/
    api/            REST routes (media, projects, jobs, exports, images, system)
    core/           settings, auth hook, path safety
    db/             SQLAlchemy models and session
    jobs/           Celery app, thread runner, progress/cancel context
    services/       media_inspector, video_analysis (SceneDetector), audio_analysis,
                    highlights, timeline (ClipSelector, TimelineBuilder), auto_color,
                    effects (EffectsComposer), renderer (FFmpegRenderer), export
                    (ExportManager), thumbnails, image_studio, graphics, sound_library,
                    detectors (plugin hook), pipeline, maintenance
    storage/        storage interface + local implementation
    presets.py, schemas.py, main.py
  alembic/          migrations
  tests/
frontend/           React app (src/pages, src/components, src/lib), Vitest tests, e2e/
scripts/            make_sample_media.py
docs/               openapi.json, examples/
docker-compose.yml, .env.example
```

## Built-in assets

The three music tracks (Beast Pulse, Neon Drive, Cinematic Rise), the transition sound effects
and the stickers are generated by this code and are public domain (CC0). No commercial songs
or game assets are bundled; upload only music and graphics you have the rights to use.
