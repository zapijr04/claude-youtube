# NOOBZY AI STUDIO -- instructions for a future coding agent

This file is scoped to `noobzy-studio/` only. The repository root
`CLAUDE.md` describes a *different* subproject (`skills/claude-youtube/`,
a Claude Code skill package) and still applies to that directory; do not
edit it as part of work in here, and do not let its rules (e.g. "Keep
SKILL.md under 500 lines") leak into this subproject's very different
architecture.

## Before changing anything

1. Read `docs/IMPLEMENTATION_STATUS.md` first. It is a row-per-feature,
   evidence-backed WORKING/PARTIAL/NOT BUILT table. Trust it over this
   file's prose if they ever disagree -- update the status table whenever
   you change what's true.
2. Read `docs/DECISIONS.md` for *why* things are built the way they are,
   including two real bugs that were found and fixed (an `astats` label
   mismatch, a pixel-variance measurement bug) and the FFmpeg expression
   evaluator's actual capabilities in this environment (`floor`/`clip` are
   NOT available; `min`/`max`/`between`/`sin`/`cos` are). Re-verify with a
   direct FFmpeg CLI probe before assuming otherwise on a different machine.
3. Run the test suite before and after your change:
   ```
   cd noobzy-studio/backend && .venv/bin/python -m pytest tests/ -q
   ```
   33 tests should pass. If you add a feature, add a test that would fail
   without it -- several bugs in this codebase were only caught because an
   assertion failed, not by eyeballing output.

## Hard rules carried over from the product spec (do not relax these)

- **Never fabricate what happened in footage.** `app/timeline/builder.py`
  has two builders on purpose: one for grounded markers (manual or
  simulated-and-labeled), one honest rough-cut fallback for ungrounded
  footage that invents zero graphics/beats/SFX. Don't add a third path that
  guesses story content without evidence.
- **Never claim a provider/credential works when it doesn't.** Every
  gated integration (ElevenLabs, RunPod, ComfyUI, GPU) must fail loud and
  clear (a specific exception or `not_configured` status) when
  unconfigured, never silently fall back to a fake success. See
  `app/audio/tts.py::ElevenLabsNotConfigured` and
  `app/compute/providers.py` for the pattern to follow.
- **No paid job without explicit approval + a spending cap.** See
  `app/compute/providers.py::submit_job`. Don't add a code path that
  bypasses `CostApproval`.
- **Don't bundle third-party audio/video assets without verifiable
  redistribution rights.** The current SFX library is 100% procedurally
  synthesized (`app/audio/sfx.py`) for exactly this reason. If you add a
  licensed asset pack, record its real license in `AudioAsset.license` and
  verify the license text yourself -- don't assume.
- **Skills are declarative data, not executable code.** A `SKILL.md`'s
  front matter is parsed with `json.loads`, never `eval`/`exec`. Keep it
  that way if you extend the skill format.
- **A user-imported skill starts disabled** (`import_user_skill_md` sets
  `enabled=False`); only an explicit `POST /skills/{id}/approve` call turns
  it on. Don't auto-enable on import.

## Architecture quick reference

- **Source of truth**: `TimelineDocument` (`app/schemas.py`). Every
  render/export reads from it; nothing else holds authoritative state about
  a project's cut, narration, graphics, motion, or SFX.
- **Persistence**: `app/db.py`, SQLite, JSON-blob-per-entity rows (see
  ARCHITECTURE.md for why). `connect()` lazily runs migrations on first use
  in any process -- you don't need to remember to call `init_db()` first,
  but calling it explicitly (as `app/main.py`'s startup hook does) is still
  fine and idempotent.
- **Render engine**: `app/render/ffmpeg_render.py`, pure FFmpeg filter
  graphs (no Remotion/Blender in this build -- see DECISIONS.md for why).
  If you add a new visual effect, write and run an isolated single-filter
  FFmpeg CLI test first to confirm the expression syntax works in the
  target FFmpeg build before wiring it into the big filter-graph string;
  debugging a 2000-character filter_complex blind is much slower.
- **Audio**: `app/audio/{sfx,sfx_library,cues,mix,tts}.py`. Procedural SFX
  → named presets → cue planner (density/cooldown) → multi-bus placement →
  real `sidechaincompress` ducking → `loudnorm` QC.
- **Frontend**: `desktop/src/`, plain React+TS+fetch, no state library. Add
  a screen under `src/screens/`, wire it into `App.tsx`'s `SCREENS` array
  and the corresponding `api.ts` client method.

## Known gaps (see IMPLEMENTATION_STATUS.md for the full, current list)

- No vision/LLM model is wired in for scene-understanding or reference-
  video style learning -- both are architecturally ready (the data
  contracts and the skill-approval loop exist) but need a real model
  adapter, which needs credentials/compute this build doesn't have.
- No Blender, no GPU, no live ComfyUI/RunPod job execution in this
  environment. The adapters exist and are honestly gated; they haven't
  been exercised against live services.
- The Electron `BrowserWindow` itself has not been opened on a real
  display (headless container). The React app was verified live via
  headless-Chromium screenshots against the running backend instead.
