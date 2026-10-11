# Architecture

## Why this shape

The build spec asked for Electron + Vite + React + TS on top of a Python
FastAPI backend with SQLite persistence, FFmpeg/Remotion-class rendering,
and a versioned skills system. That's what's here, with two adjustments
made for the actual environment this was built in (a headless Linux
container, no display, no GPU):

- **Remotion was not used.** Remotion renders React compositions to video
  via a headless Chromium + FFmpeg pipeline; standing that up reliably in
  this container, on top of an already-large scope, was a worse bet than a
  direct FFmpeg filter-graph renderer. Every effect the spec asks for
  (cuts, zoom, shake, alpha-composited cutouts, kinetic captions, counters,
  timers, reframing) is implemented as real FFmpeg filters instead,
  verified against this build's actual filter/eval capabilities (see
  DECISIONS.md). This is a legitimate substitution, not a downgrade in
  what's proven: every render in the test suite is a real, ffprobe-verified
  MP4.
- **Blender, ComfyUI, and RunPod are not available in this container**
  (no Blender install, no GPU, no network path to a user's local ComfyUI).
  Their adapters are implemented and gated (see `app/compute/providers.py`)
  but report `not_configured` honestly rather than being faked.

## Data flow

```
 MP4/MOV  --ffprobe-->  SourceMedia
          --scene filter-->  scene-cut windows (real pixel-diff detection)
          --manual/simulated markers (when available)-->  grounded StoryBeats

 TimelineDocument (the single source of truth)
   scenes[]      -- source in/out, evidence_kind, confidence
   beats[]       -- story structure, each tied to scene_ids
   narration[]   -- text + provider + alignment, grounded_in_timestamps
   graphics[]    -- counters/timers/cards, time-windowed
   motion[]      -- zoom/shake, time-windowed
   sound_cue_plan -- SoundCue[] with category, timing, evidence

          |
          v
 Render engine (app/render/ffmpeg_render.py)
   trim+concat scenes -> motion filters -> alpha cutout overlay
   -> drawtext captions/graphics -> (reframe for Shorts) -> mux final audio

 Audio pipeline (app/audio/*)
   procedural SFX (NumPy) -> cue planner (density/cooldown) -> placed on bus
   narration (ElevenLabs or local fallback) -> voice bus
   source game audio -> game bus
   procedural music loop -> music bus --sidechaincompress (duck vs voice)-->
   mix_stems -> loudnorm QC -> final mixed track -> render engine's -map

          |
          v
 Export (app/export/*): MP4 (from render), SRT, TimelineDocument.json,
 OTIO, FCPXML (each round-trip verified immediately after writing)
```

## Why a TimelineDocument, and why JSON-blob SQLite tables

`TimelineDocument` (app/schemas.py) is exactly the typed, versioned
document the spec asks for: every render and every export derives from it,
nothing else. Persistence (app/db.py) stores each top-level entity
(`Project`, `SourceMedia`, `TimelineDocument`, `SkillManifest`,
`MemoryRecord`, ...) as an indexed-by-id row holding that entity's full
Pydantic JSON serialization, rather than a fully normalized relational
schema for deeply nested documents. This keeps the TimelineDocument
trivially round-trippable (load it, mutate it in Python with the same
Pydantic model, save it back) while still being real, queryable, durable
SQLite with a (minimal but real) numbered-migration mechanism -- not an
in-memory mock and not a destructive `create_all`.

## Honesty boundaries baked into the code, not just docs

- `app/timeline/builder.py` has two builders on purpose:
  `build_timeline_from_events` (consumes manual or simulated markers --
  real story structure) and `build_rough_cut_from_scene_cuts` (no markers
  available -> neutral scene windows, zero invented graphics/beats/SFX,
  narration left as an explicit `[Add narration...]` placeholder). The
  FastAPI `/analyze` endpoint always calls the second one, because this
  build has no vision model to ground a real story in; wiring the first one
  in without that evidence would mean inventing what happened in the
  footage, which the spec explicitly forbids.
- `app/audio/tts.py`'s local fallback is a formant-ish amplitude-modulated
  tone, not speech, and every `NarrationBlock` it touches is tagged
  `is_placeholder_voice=True`. The ElevenLabs path makes a real documented
  API call and raises `ElevenLabsNotConfigured` (caught and surfaced, never
  swallowed into a fake success) when no key is present.
- `app/compute/providers.py` detects GPU/ComfyUI/RunPod availability for
  real (subprocess/`urllib`/env checks) and reports `not_configured` with
  the exact missing prerequisite instead of simulating a job.

## Frontend

Plain React + TypeScript (no state library) talking to the FastAPI backend
over `fetch`. Eleven screens matching the spec's list, each backed by a
real endpoint call -- there is no screen that renders mock data. See
`desktop/src/lib/api.ts` for the typed client and
`docs/IMPLEMENTATION_STATUS.md` for how the UI was verified to actually
render (headless Chromium screenshots against the live backend, since this
container has no display for the real Electron window).
