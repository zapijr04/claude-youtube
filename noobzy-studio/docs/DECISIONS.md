# Decisions log

Running log of notable choices made while building NOOBZY AI STUDIO, most
recent first-built at the bottom of each section is not implied -- entries
are grouped by subsystem.

## Scope for this build

- Built this as a genuinely new subproject (`noobzy-studio/`) inside the
  existing `claude-youtube` repo, alongside (not replacing) the existing
  `skills/claude-youtube/` Claude Code skill package, per the explicit
  instruction to preserve and extend the existing workspace rather than
  destroy it.
- Prioritized a real, tested, end-to-end vertical slice (Phases 1-3 of the
  spec's delivery plan) over partial coverage of all four phases. Phase 4
  (ComfyUI/RunPod generative video, heavier tracked-character effects) is
  implemented as honestly-gated stubs, not faked.

## Render engine: FFmpeg filters, not Remotion

Remotion renders through a headless-Chromium-plus-FFmpeg pipeline designed
for a desktop/CI environment with predictable browser automation. Standing
that up reliably here, on top of everything else in scope, was worse risk
than building the render engine directly on FFmpeg's own filter graph --
which is what Remotion itself eventually shells out to for the actual
encode. Every requested effect (cuts, zoom, shake, alpha cutout overlay,
kinetic captions, counters/timers, 9:16 reframe) has a real, verified
FFmpeg filter implementation in `app/render/ffmpeg_render.py`.

## `floor`/`clip` are not available in this FFmpeg build's expr evaluator

Discovered by direct CLI probing (not assumed): this environment's FFmpeg
(6.1.1-3ubuntu5) filter expression evaluator accepts `min`/`max`/`between`/
`sin`/`cos` but errors on `floor(...)` and `clip(...)` inside `crop`'s
w/h/x/y expressions ("Error when evaluating the expression"). All easing
and windowing in the motion/zoom/shake filters uses
`min(max(x,0),1)`-style clamps and `between(t,a,b)` gating instead. This
was verified with isolated single-filter FFmpeg CLI tests before being
wired into the render pipeline, to avoid debugging a 2000-character
filter-graph string blind.

## Apostrophes are stripped from on-screen text, not escaped

`drawtext`'s `text='...'` value and the first-level filtergraph quoting
both use single quotes; nesting a literal apostrophe with
backslash-escaping broke the parser ("Error parsing global options") on a
caption containing "here's". Rather than hand-roll FFmpeg's two-level
escaping rules under time pressure, `_esc_text()` drops apostrophes
entirely. Acceptable for on-screen captions/graphics; would need the
backslash-doubling approach if the spec required apostrophes preserved
exactly.

## Scene-cut detection: FFmpeg `scene` filter, not PySceneDetect/OpenCV

`select='gt(scene,T)'` + `showinfo` gives a real per-frame scene-change
score from actual pixel differences, parsed from stderr `pts_time`. This
avoids an OpenCV/PySceneDetect dependency for the MVP. Measured against the
synthetic fixture's known ground-truth cut points, it found 6 of 7 true
cuts, missing a black-to-dark-green transition (both segments have low
luma, so the scene score didn't cross threshold) -- a real, expected
limitation of luma-based scene detection, not a result that was tuned or
cherry-picked to look better than it is. `tests/test_media_pipeline.py`
asserts "most, not all" cuts are found for exactly this reason.

## Audio: NumPy-synthesized SFX, not a bundled sound library

Could not verify redistribution rights for any third-party SFX pack in
this environment, and the spec says explicitly: when redistribution is
unclear, do not bundle. Every SFX asset is generated at runtime from sine/
sweep/noise waveforms (`app/audio/sfx.py`), licensed
`procedurally_generated` in `AudioAsset` metadata -- zero copyright risk,
and it sidesteps the licensing question rather than working around it.
Background music is the same: a locally synthesized pad+arpeggio loop, not
a licensed or copyrighted track.

## `astats` RMS measurement bug (caught by a failing test, not assumed correct)

First RMS-ducking measurement returned `-inf` for a clearly audible file.
Root cause: FFmpeg's `astats` filter label is `RMS level dB:` in this
build, not `RMS_level=` (what an older/different version prints); the regex
was matching nothing. Verified the real label with a raw CLI probe before
fixing `app/audio/mix.py`. A second bug in the render-quality test (not the
app code) computed pixel "variance" over interleaved RGB bytes directly,
which measures R/G/B channel differences rather than actual spatial detail
-- a flat solid-color frame showed high "variance" while a text-containing
frame showed lower, backwards from what the test intended. Fixed by
converting to per-pixel luma before computing spatial standard deviation.
Both are recorded here because they were caught by assertions failing, not
by eyeballing output -- which is the point of the automated test suite.

## OTIO FCPXML adapter

Base `opentimelineio` ships only `otio_json`/`otioz`/`otiod` adapters; FCPXML
support needed the separate `otio-fcpx-xml-adapter` package (pip-installable,
no API key, no network dependency beyond the initial install). Added to
`requirements.txt`. Both OTIO and FCPXML exports are round-trip verified
(read back immediately after writing) in code, not just in tests.

## Skills: declarative Markdown + JSON manifest, not executable code

Per the spec's explicit constraint ("declarative recipes/preferences and
trusted built-in primitives, NOT arbitrary executable scripts"), a skill is
a `SKILL.md` front-matter block (id/title/triggers/capabilities/
dependencies/allowed_parameters/examples) parsed with a plain JSON parser --
nothing is `eval`'d or executed from a skill file. A user-imported skill is
staged `enabled=False` until an explicit approval call, per the "preview
and approve before activation" requirement.

## Persistence: JSON-blob rows + a minimal real migration mechanism

See ARCHITECTURE.md. Chose indexed-by-id rows holding full Pydantic JSON
over a fully normalized schema, specifically so the TimelineDocument (the
one artifact every export derives from) never needs a lossy relational
round-trip. A `schema_migrations` table plus ordered, idempotent SQL
scripts stands in for a full Alembic setup -- real and append-only, not a
destructive `create_all()`, but simpler than the spec's "with migrations"
language might imply for a production system; documented as a conscious
scope cut, not hidden.

## Electron GUI: built and typechecked, not visually run

This container has no display server. The React renderer was verified
*live* -- `npm run dev` (Vite) against the real running FastAPI backend,
screenshotted with headless Chromium (`/opt/pw-browsers/chromium`,
pre-installed in this environment) clicking through Home -> Import ->
Skills Lab and confirming the Skills Lab table shows all 24 real skills
fetched over HTTP. The Electron *shell* (`main.ts`/`preload.ts`) compiles
clean under `tsc` and the packaged main process launches without error, but
opening an actual `BrowserWindow` on-screen has not been done here --
recorded honestly in IMPLEMENTATION_STATUS.md as PARTIAL, not WORKING.
