# NOOBZY AI STUDIO

A local-first desktop video-editing application for the NOOBZY Roblox
channel: import real gameplay, get a grounded rough cut, add narration
(ElevenLabs or a local placeholder), procedurally-synthesized SFX with
automatic placement, mixed and ducked audio, kinetic captions and motion
graphics, and export a real MP4 plus a DaVinci-compatible cutlist.

This lives inside the `claude-youtube` repo (a separate Claude Code skill
package -- see the repo root `README.md`/`CLAUDE.md`) as its own
self-contained subproject. It does not modify or depend on `skills/claude-youtube/`.

See `docs/IMPLEMENTATION_STATUS.md` for exactly what works today, with
proof (code path, command, test result) for every claim, and
`docs/ARCHITECTURE.md` / `docs/DECISIONS.md` for how and why it's built
this way.

## Layout

```
noobzy-studio/
  backend/            Python 3.11+ FastAPI backend (the real engine)
    app/
      schemas.py       Typed data contracts (Project, TimelineDocument, ...)
      db.py             SQLite persistence + migrations
      media/            ffprobe, thumbnails/waveform/proxy, scene-cut detection
      timeline/         TimelineDocument builder (grounded rough cuts) + retime.py (speed ramps, narration resync)
      render/           FFmpeg render engine (cuts, motion, overlays, captions, timer, arrow)
      audio/            Procedural SFX synth, cue planner (incl. pitch/speed), multi-bus mix/ducking, TTS
      skills/           Skill loader/validator/importer
      learning/         Reference-video pacing analysis -> proposed skill (point 4)
      memory/           Persistent memory store
      export/           SRT, OTIO, FCPXML export
      compute/          Compute provider abstraction (local/GPU/ComfyUI/RunPod)
      pipeline.py       The one render pipeline: render_preview (cache-only) vs. render_final_export
                        (the only code path allowed to write into a project's output folder)
      main.py           FastAPI app wiring every module together
    tests/              pytest suite (37 tests) incl. synthetic fixture generator and the
                        Point 6 non-destructive-editing regression test
  desktop/            Electron + Vite + React + TypeScript desktop shell
  skills_library/     24 built-in versioned skills (SKILL.md + manifest.json)
  docs/               ARCHITECTURE.md, IMPLEMENTATION_STATUS.md, DECISIONS.md
  .env.example
```

## Quick start

### 1. Backend (required)

```bash
cd noobzy-studio/backend
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8077
```

The backend seeds the 24 built-in skills into `skills_library/` and a local
SQLite DB (`backend/data/noobzy.db`) on first startup. Visit
`http://127.0.0.1:8077/docs` for the live OpenAPI UI.

Optional: copy `.env.example` to `backend/.env` and fill in
`ELEVENLABS_API_KEY`/`ELEVENLABS_VOICE_ID` for real narration (see
`docs/IMPLEMENTATION_STATUS.md` for what works without it).

### 2. Desktop UI

```bash
cd noobzy-studio/desktop
npm install
npm run dev        # Vite dev server at http://localhost:5173
```

In dev mode, open that URL in a browser (or `npm run electron` for the
actual Electron window, once built with `npm run build:electron` --
**note:** the Electron GUI window itself has not been visually verified in
this headless build environment; the React app was verified live and
working by loading it in headless Chromium against the real backend, see
`docs/IMPLEMENTATION_STATUS.md`).

To package the Electron main process:
```bash
npm run build          # renderer -> dist/
npm run build:electron # main/preload -> electron-dist/
npm run electron        # launches the Electron window (needs a display)
```

### 3. Run the tests

```bash
cd noobzy-studio/backend
.venv/bin/python -m pytest tests/ -v
```

37 tests, all passing as of this build -- see `docs/IMPLEMENTATION_STATUS.md`
for the full breakdown and what each one proves.

### 4. Try it end-to-end with curl

Editing is non-destructive: every change is saved to the project's
`TimelineDocument` (with full version history) and only shows up as a real
MP4 via an explicit **Preview** (cheap, cached, written only to the app's
cache) or **Export Final Video** (the one action that writes a finished
MP4 to your chosen output folder) call -- never on every edit.

```bash
# Generate the synthetic test fixtures (clearly-labeled synthetic gameplay)
.venv/bin/python tests/fixtures/make_fixture.py

PID=$(curl -s -X POST localhost:8077/projects -H 'Content-Type: application/json' \
  -d '{"name":"Demo","preset":"LONG_FORM_STORY","target_duration_sec":75}' | python3 -c "import json,sys;print(json.load(sys.stdin)['id'])")

MID=$(curl -s -X POST "localhost:8077/projects/$PID/media" \
  -F "file=@tests/fixtures/generated/fixture_long.mp4;type=video/mp4" | python3 -c "import json,sys;print(json.load(sys.stdin)['id'])")

curl -s -X POST "localhost:8077/projects/$PID/analyze?media_id=$MID"

# Cheap, cached preview -- writes ONLY to backend/data/cache/, never to an output folder.
curl -s -X POST "localhost:8077/projects/$PID/preview" -H 'Content-Type: application/json' \
  -d "{\"media_id\":\"$MID\"}"

# The ONE action that writes a finished MP4 (+ stems + SRT/OTIO/FCPXML/timeline.json)
# to backend/data/exports/<project_id>/ by default, or wherever you pass as output_dir.
curl -s -X POST "localhost:8077/projects/$PID/export/final-video" -H 'Content-Type: application/json' \
  -d "{\"media_id\":\"$MID\"}"
```

This produces a real rendered MP4 under `backend/data/renders/<project_id>/final.mp4`.

## What requires credentials or paid cloud compute

- **Real ElevenLabs narration**: `ELEVENLABS_API_KEY` + `ELEVENLABS_VOICE_ID`.
  Without them, narration uses an audible local placeholder tone (not real
  speech), clearly tagged `is_placeholder_voice: true` everywhere.
- **RunPod cloud GPU jobs**: `RUNPOD_API_KEY`, plus an explicit
  `CostApproval` with a spending cap on every paid submission. Nothing
  spends money without that.
- **ComfyUI local AI image/video workflows**: a running ComfyUI instance at
  `COMFYUI_URL` that you installed yourself.

Everything else -- import, scene detection, rough-cut timeline building,
procedural SFX, audio mixing/ducking/loudness QC, motion graphics, kinetic
captions, MP4 rendering, OTIO/FCPXML/SRT export, the skills library, and
persistent memory -- works fully offline with no credentials.
