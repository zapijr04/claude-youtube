# Implementation Status

Last verified: this build, `backend/.venv/bin/python -m pytest tests/ -q`
→ **33 passed**, 0 failed, run twice in a row for stability.

Labels: **WORKING** (built, run, and verified with evidence below) /
**PARTIAL** (built and partially verified, with a stated gap) / **NOT
BUILT** (not implemented, with the exact prerequisite to add it).

No row below claims a credential, model, or compute resource this
environment doesn't actually have. Where ElevenLabs/RunPod/ComfyUI/GPU/
Blender/DaVinci are involved, the gap is stated explicitly.

## Phase 1 -- core pipeline

| Feature | Status | Proof |
|---|---|---|
| Scaffold (backend + desktop) preserving existing `skills/claude-youtube/` | WORKING | `noobzy-studio/` is a sibling directory; `git status` shows no changes under `skills/claude-youtube/`. |
| Dependency discovery | WORKING | Audited at session start: Node v22.22.0, Python 3.13.16, FFmpeg 6.1.1 (libx264/libx265/aac), no Blender, no `nvidia-smi`. Drove every subsequent design choice (see DECISIONS.md). |
| Desktop UI (Electron+Vite+React+TS) | PARTIAL | Builds and typechecks clean (`npm run typecheck`, `npm run build`, `npm run build:electron` all exit 0). React app verified **live and working** against the real backend via headless Chromium screenshots (Home → create project → Import screen → Skills Lab showing 24 real skills fetched over HTTP). The actual Electron `BrowserWindow` has not been opened on-screen -- this container has no display server. |
| Backend (FastAPI) | WORKING | `app/main.py`, 24 routes. `uvicorn app.main:app` starts; exercised live via `curl` and via `fastapi.testclient.TestClient` in `tests/test_api_e2e.py`. |
| Persistent projects (SQLite + migrations) | WORKING | `app/db.py`. Numbered, idempotent migration scripts + a `schema_migrations` table. `tests/test_skills_persistence.py::test_skills_survive_separate_process_restart` proves durability across a genuine separate `python` process, not just in-memory state. |
| Video import + FFprobe validation | WORKING | `app/media/ffprobe_util.py`. `tests/test_media_pipeline.py::test_probe_detects_real_codec_duration_fps` and the live HTTP upload in `test_api_e2e.py`. |
| Thumbnails / waveform / proxy generation | WORKING | `app/media/proxy.py`. `test_thumbnails_and_waveform_are_real_files` checks real non-trivial file sizes. |
| Scene/shot detection | WORKING (with a known, honest limitation) | `app/media/scenes.py`, FFmpeg's real `scene` filter. Against the synthetic fixture's known ground truth, finds 6 of 7 true cuts, documented in DECISIONS.md (misses one low-contrast dark-to-dark transition -- a real limitation of luma-based detection, not hidden). |
| Candidate highlight windows with source timestamps | WORKING | `app/media/scenes.py::build_scene_windows`. |
| Editable Storyboard | WORKING | Storyboard screen renders every `StoryBeat` with its cited source timestamp and evidence; backed by `GET /projects/{id}/timeline`. |
| Timeline rough cut | WORKING | `app/timeline/builder.py`, two honest variants: `build_timeline_from_events` (grounded in manual/simulated markers) and `build_rough_cut_from_scene_cuts` (no markers -- neutral windows, zero invented content). The `/analyze` endpoint always uses the second for real, unannotated footage. |
| FFmpeg real render (16:9 and 9:16) | WORKING | `app/render/ffmpeg_render.py`. `tests/test_render.py::test_long_form_render_is_valid_16x9_mp4` (1920x1080, ffprobe-verified) and `test_short_form_render_is_valid_vertical_mp4` (1080x1920). |
| Local animation overlay | WORKING | Alpha-channel cutout PNG composited with `overlay`, verified moving and correctly alpha-blended by direct frame inspection (see below). |
| Tests (automated) | WORKING | `backend/tests/`, 33 tests, `pytest` exit 0. |

## Phase 2 -- script, narration, SFX, captions, manual editing, DaVinci export

| Feature | Status | Proof |
|---|---|---|
| Scene-grounded script writing | PARTIAL | `app/timeline/builder.py` writes narration text grounded in source timestamps when markers exist (`grounded_in_timestamps` on every `NarrationBlock`, asserted in `test_build_from_simulated_events_grounds_every_beat`). No LLM is wired in this build to generate that text from unannotated footage -- see "Scene-understanding LLM" below. |
| Continuous narration planner / voice-coverage QA | PARTIAL | `NarrationBlock.duration_sec`/`output_start_sec` are tracked per beat and the rough-cut builder leaves an explicit `[Add narration...]` placeholder for ungrounded scenes rather than inventing coverage. A dedicated gap-detector report (flagging silent stretches > a configurable threshold across the *final mixed audio*, not just planned narration) is **NOT BUILT** -- `app/audio/mix.measure_rms_db` gives the primitive to build it on, but no endpoint assembles the report yet. |
| ElevenLabs connection + caching + timestamps | WORKING (code path) / UNVERIFIED (live) | `app/audio/tts.py::synthesize_elevenlabs` calls the real documented `POST /v1/text-to-speech/{voice_id}/with-timestamps` endpoint and parses character-level alignment into word timings. **Genuinely unverified against the live ElevenLabs API** -- no API key is configured in this environment. Verified instead via the fixture path: `synthesize_elevenlabs` correctly raises `ElevenLabsNotConfigured` (not a fake success) when the key is absent, asserted in manual testing and exercised by every render in the test suite via the fallback branch. |
| Local TTS fallback (offline) | WORKING, clearly labeled placeholder | `app/audio/tts.py::synthesize_local_fallback`. No Piper/espeak-ng is installed in this environment (checked: `which espeak-ng espeak` → none); the fallback renders an audible, speech-shaped amplitude-modulated tone, not real speech, and every block is tagged `is_placeholder_voice=True`. `tests/test_sfx_and_mix.py::test_music_ducks_measurably_under_narration` uses this path and proves it's real, audible audio (not silence). |
| Selective captions | WORKING | `app/render/ffmpeg_render.py::select_kinetic_caption_words` picks emphasis words (len≥5, stopword-filtered) from real word alignment, capped at `max_words`. Rendered and visually confirmed (frame grabs showing "TRIED", "SPOTS", etc. appearing only in their timing windows). |
| Full-subtitle accessibility toggle | WORKING | `app/export/srt_export.py::export_full_srt` vs `export_selective_srt`; both exercised in `tests/test_export_formats.py`. |
| Automatic SFX library + cue placement | WORKING | `app/audio/sfx.py` (13 procedurally-synthesized sounds, NumPy, zero license risk) + `app/audio/cues.py` (26 named presets across 18 categories, per-category cooldown, density cap). `test_sfx_cue_planner_expands_at_least_four_distinct_audible_cues` proves cues are not just planned but **audible** in the mixed bus (measured RMS > -50dB at each cue's timestamp). |
| Audible music ducking | WORKING | `app/audio/mix.py::duck_against_voice`, real FFmpeg `sidechaincompress`. `test_music_ducks_measurably_under_narration` measures ~19dB of real level drop under a narration window (not a volume keyframe approximation). |
| Manual editing tools (trim/reorder/swap/undo) | PARTIAL | The TimelineDocument is fully editable via `PUT /projects/{id}/timeline` (whole-document replace) and the Storyboard/Motion Studio screens display it live. Per-field inline editing UI (drag-trim a clip, reorder beats, undo/redo stack) is **NOT BUILT** -- the data model and persistence support it; the UI affordances do not exist yet. |
| DaVinci timeline export | WORKING (export) / NOT VERIFIED (Resolve GUI import) | `app/export/otio_export.py` builds a real OTIO timeline from the TimelineDocument's scenes + story-beat markers, exports both `.otio` and `.fcpxml` (via `otio-fcpx-xml-adapter`), and **round-trips each file through OTIO's own reader immediately after writing** (`tests/test_export_formats.py`). Whether DaVinci Resolve's GUI actually imports the FCPXML has **not been tested** -- there is no Resolve installation in this environment, and this is stated plainly rather than assumed. |

## Phase 3 -- memory, skills, learning, advanced SFX/QC

| Feature | Status | Proof |
|---|---|---|
| Persistent memory engine | WORKING | `app/memory/store.py` + `app/db.py`. Versioned records (`test_memory_versions_increment_on_update`), feedback logging, export/import to JSON. |
| Versioned Skills Lab | WORKING | `app/skills/loader.py` + `skills_library/` (24 built-in skills, SKILL.md front-matter + manifest.json). Enable/disable, version history (`test_skill_version_history_is_kept_on_update`), persistence across a real separate process restart. |
| Import a new skill from Markdown, preview+approve | WORKING | `loader.import_user_skill_md` validates front matter (raises `ValueError` on malformed input, `test_import_user_skill_md_validates_front_matter`), stages it `enabled=False`, and `POST /skills/{id}/approve` flips it on. Exercised over real HTTP in the Skills Lab screen (file input → `POST /skills/import`). |
| Reference-video style learning | NOT BUILT | `noobzy-reference-learner` / `noobzy-teach-from-video` skills are seeded (declarative recipe only); the actual frame/audio analysis pipeline that turns an uploaded tutorial video into a proposed `CreativeStyleProfile` is not implemented. Building it needs: frame sampling + shot/transition detection (reuse `app/media/scenes.py`), caption-region heuristics, and a review/approve UI step mirroring the skill-import flow. No vision/LLM model is configured in this environment to do the semantic part. |
| Creative Brief interface | WORKING (as a deterministic matcher, not full NLU) | `app/creative_brief.py`: ~9 regex rules covering the spec's example intents ("more suspense", "three less meme sounds", "keep talking during travel", "make this a short", caption-mode toggles, "learn this style"). Unmatched text returns `{"action": "unrecognized", ...}` rather than guessing -- verified in `test_creative_brief_parses_known_intents_and_flags_unknown` and live over HTTP. This is explicitly a small rule matcher, not a language model, and is documented as such everywhere it's referenced. |
| Adapt from corrections / feedback → suggested skill updates | PARTIAL | Every creative-brief parse is recorded via `memory.record_feedback` with provenance (`CreativeFeedbackRecord`). Turning a pattern of accepted/rejected feedback into an actual *proposed skill version diff* (the "one-click approval" loop) is **NOT BUILT** -- the data is captured; the synthesis step is not. |
| Per-channel styles / per-project overrides | PARTIAL | `MemoryRecordKind.channel_profile` / `creator_preference` / `editing_rule` exist and are exercised (`test_memory_versions_increment_on_update`). No UI screen yet surfaces "apply channel profile X to this project" as a one-click action. |
| Advanced SFX Studio (A1-A4) | WORKING for the achievable scope | Sound Library: 13 procedural + 1 music-loop asset, each with `AudioAsset.license` metadata (all `procedurally_generated`, zero redistribution risk -- no third-party pack was bundled because its license couldn't be verified here, per spec). 26 named presets across 18 trigger categories (`app/audio/cues.py`), density (light/balanced/high-energy), per-category cooldown, max-per-minute cap. Multi-bus mix (voice/SFX/game/music), real sidechain ducking, `loudnorm`+`volumedetect`-based QC report (LUFS, true peak, clipping). **Not built**: ElevenLabs Sound Effects / other paid SFX-generation provider integration (no such adapter exists yet; would be gated the same way RunPod is). |
| Loudness/clipping QC | WORKING | `app/audio/mix.py::loudness_report` + `normalize_to_target`. `test_loudness_report_hits_target_and_detects_no_clipping`: normalized output lands within 1.5 LUFS of a -14 LUFS target with `clipping_detected=False`. |

## Phase 4 -- optional ComfyUI / RunPod / advanced generative

| Feature | Status | Proof |
|---|---|---|
| Compute Providers abstraction | WORKING | `app/compute/providers.py`. `local_cpu` always available; `local_gpu` genuinely detected via `nvidia-smi` (absent in this container → honestly reports unavailable, not simulated); `comfyui_local`/`runpod_gpu` check real env vars / HTTP reachability. |
| Cost-gated paid job submission | WORKING | `submit_job` blocks on `ComputeJobStatus.awaiting_cost_approval` until an explicit `CostApproval(approved_by_user=True)` is supplied, and refuses (`failed`) if the estimate exceeds the approved cap -- `tests/test_compute_and_memory.py::test_paid_job_blocked_without_explicit_cost_approval` and `test_cost_over_approved_cap_is_refused`. No job is ever actually dispatched to RunPod/ComfyUI in this build (both report `not_configured`/no live executor) -- no network credentials for either exist here. |
| ComfyUI / RunPod generative video | NOT BUILT (intentionally gated) | No model execution, no API calls beyond a reachability/auth check. Needs a user-supplied `COMFYUI_URL` (running instance) or `RUNPOD_API_KEY` plus a real job-submission implementation against RunPod's current API -- neither is present or claimed to work here. |
| Blender scripted renders / 3D compositing | NOT BUILT | No Blender installation in this environment (`which blender` → none). `noobzy-character-anim` is seeded as a skill recipe only; the actual cutout is a synthetic alpha-PNG placeholder shape (clearly labeled, see `app/render/overlays.py`), not a segmented/tracked Roblox character -- segmentation would need a vision model this environment doesn't have. |

## Section 8D acceptance-test checklist (synthetic fixtures)

All items below are exercised in `backend/tests/` against
`tests/fixtures/make_fixture.py`'s generated synthetic (explicitly labeled,
never claimed to be real footage) fixtures:

- [x] Short: 3 simulated egg openings, 9:16, local-fallback VO, first-3s
      hook, reveal SFX per egg, one anticipation riser, selective captions,
      end comparison card. `test_short_form_render_is_valid_vertical_mp4`,
      `test_short_form_has_three_egg_events_with_sfx`.
- [x] Long: separate 16:9 fixture (0/6→6/6 counter, timer-less but chase/
      fail/payoff beats), 4+ synchronized distinct SFX events.
      `test_long_form_render_is_valid_16x9_mp4`,
      `test_long_form_sfx_cues_are_audible_in_final_mix`
      (7-9 audible cues depending on density, always ≥4).
- [x] Real audible MP4 with SFX + local-fallback narration + procedurally
      generated music loop, FFprobe-verified. Every render test probes the
      output file.
- [x] Music ducking measured before/after narration windows; LUFS/true-peak
      report. `test_music_ducks_measurably_under_narration`,
      `test_loudness_report_hits_target_and_detects_no_clipping`.
- [x] Visual composite test: moving synthetic test subject (alpha-blended
      cyan circle, explicitly labeled a placeholder, not a real character)
      with correct alpha rendering + a counter overlay + a kinetic word,
      confirmed both visually (frame grabs) and by an automated per-pixel
      luma-variance check scoped to the counter's exact time window
      (`test_long_form_counter_graphic_appears_only_in_its_window`).
- [x] Load a reference-lesson-*shaped* skill file (SKILL.md), approve it,
      persist it, kill/restart the process, retrieve it, apply it to a
      second project. `test_skills_survive_separate_process_restart`,
      `test_import_user_skill_requires_approval_before_enabled`. (Note:
      this proves the *skill* persistence/approval loop; it does not prove
      automated *reference-video analysis*, which is NOT BUILT as noted
      above.)
- [x] From a short simulated rough-cut, build a story-driven cut with
      source-timecode evidence plus a corresponding VO/SFX/graphics plan.
      `test_build_from_simulated_events_grounds_every_beat`.
- [x] Export full MP4, stems (voice/sfx/game/music bus WAVs), source
      timestamp cutlist (TimelineDocument.json), SRT (selective + full
      toggle), and OTIO/FCPXML. Sync/round-trip verified; Resolve GUI
      import explicitly NOT claimed as tested.

## Known bugs found and fixed during this build (left in DECISIONS.md for traceability)

- `astats` RMS-measurement regex matched the wrong label for this FFmpeg
  build (`RMS level dB:` vs. assumed `RMS_level=`), silently returning
  `-inf`; caught because the ducking assertion failed, not assumed correct.
- A render-quality test computed "pixel variance" over interleaved RGB
  bytes directly, which measures channel differences rather than spatial
  detail and gave backwards results for a flat vs. a text-containing frame;
  fixed to convert to per-pixel luma first.
- `app/db.py` functions assumed some caller had already run migrations;
  a fresh/wiped DB file hit `sqlite3.OperationalError: no such table` when
  used standalone. Fixed with a lazy, idempotent schema-init guard in
  `connect()` so the module is safe to use from any entry point, not only
  behind the FastAPI startup hook.

## Lint / typecheck / test commands actually run for this build

```
cd noobzy-studio/backend && .venv/bin/python -m pytest tests/ -q
  → 33 passed (run twice for stability)

cd noobzy-studio/desktop && npm run typecheck
  → tsc -p tsconfig.json --noEmit && tsc -p electron/tsconfig.json --noEmit  (exit 0)

cd noobzy-studio/desktop && npm run build
  → vite build: 43 modules transformed, dist/ written (exit 0)

cd noobzy-studio/desktop && npm run build:electron
  → electron-dist/main.js, electron-dist/preload.js written (exit 0)
```

No Python linter (ruff/flake8) or JS linter (eslint) is configured in this
build -- not run, not claimed to have been run.
