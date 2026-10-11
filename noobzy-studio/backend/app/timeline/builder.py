"""Builds a typed TimelineDocument from grounded scene/event evidence.

Per the product spec, when a full vision model isn't configured the honest
path is to request timeline markers (manual or, for test fixtures,
explicitly simulated annotations) and build a rough cut from those -- never
to fabricate what happened. This builder consumes exactly such evidence:
either `AnalyzedEvent`/`Scene` objects coming from real scene-cut detection
(app.media.scenes), or an explicit list of {at_sec, label, kind} markers
(manual or simulated-fixture annotations), and turns them into beats,
narration placeholders, graphics, motion and sound cues -- all carrying
their evidence_kind/confidence so nothing is presented as more certain than
it is.
"""
from __future__ import annotations

from app.schemas import (
    AspectPreset,
    AudioTrack,
    AudioTrackKind,
    EvidenceKind,
    GraphicLayer,
    GraphicLayerKind,
    MotionPreset,
    MotionPresetKind,
    NarrationBlock,
    Scene,
    SoundCue,
    SoundCueCategory,
    SoundCuePlan,
    StoryBeat,
    StoryBeatKind,
    TimelineDocument,
)

# Maps a fixture/annotation "kind" string to the downstream planning rules.
# This table is the one place that encodes "what a Noobzy edit does with a
# given story beat" -- it's intentionally explicit rather than inferred.
_KIND_RULES: dict[str, dict] = {
    "hook": dict(beat=StoryBeatKind.hook, sfx=None, motion=None, graphic=None),
    "goal": dict(beat=StoryBeatKind.goal, sfx=SoundCueCategory.TEXT_POP, motion=None,
                 graphic=(GraphicLayerKind.counter, {"label": "EGGS STOLEN", "value": "0/6"})),
    "chase": dict(beat=StoryBeatKind.attempt, sfx=SoundCueCategory.CHASE, motion=MotionPresetKind.shake,
                  graphic=(GraphicLayerKind.cutout_overlay, {"note": "synthetic moving test subject"})),
    "near_miss": dict(beat=StoryBeatKind.complication, sfx=SoundCueCategory.NEAR_MISS, motion=MotionPresetKind.zoom,
                       graphic=None),
    "fail": dict(beat=StoryBeatKind.setback, sfx=SoundCueCategory.STEAL_FAILED, motion=None, graphic=None),
    "strategy": dict(beat=StoryBeatKind.strategy, sfx=SoundCueCategory.TRANSITION, motion=None, graphic=None),
    "climax": dict(beat=StoryBeatKind.climax, sfx=SoundCueCategory.BIG_REVEAL, motion=MotionPresetKind.zoom,
                    graphic=(GraphicLayerKind.counter, {"label": "EGGS STOLEN", "value": "6/6"})),
    "payoff": dict(beat=StoryBeatKind.outcome, sfx=SoundCueCategory.FINAL_PAYOFF, motion=None,
                   graphic=(GraphicLayerKind.end_screen, {"text": "ALL 6 EGGS STOLEN"})),
    # short-form egg reveal fixture kinds
    "egg_anticipation_1": dict(beat=StoryBeatKind.hook, sfx=None, motion=None, graphic=None),
    "egg_reveal_1": dict(beat=StoryBeatKind.mini_hook, sfx=SoundCueCategory.EGG_OPEN, motion=MotionPresetKind.zoom,
                          graphic=(GraphicLayerKind.hero_card, {"text": "COMMON EGG"})),
    "egg_anticipation_2": dict(beat=StoryBeatKind.complication, sfx=None, motion=None, graphic=None),
    "egg_reveal_2": dict(beat=StoryBeatKind.mini_hook, sfx=SoundCueCategory.EGG_OPEN, motion=MotionPresetKind.zoom,
                          graphic=(GraphicLayerKind.hero_card, {"text": "RARE EGG"})),
    "egg_anticipation_3": dict(beat=StoryBeatKind.climax, sfx=None, motion=None, graphic=None),
    "egg_reveal_3": dict(beat=StoryBeatKind.outcome, sfx=SoundCueCategory.BIG_REVEAL, motion=MotionPresetKind.zoom,
                          graphic=(GraphicLayerKind.hero_card, {"text": "LEGENDARY EGG!!"})),
    "comparison": dict(beat=StoryBeatKind.outcome, sfx=SoundCueCategory.TRANSITION, motion=None,
                        graphic=(GraphicLayerKind.comparison_card, {"text": "3 EGGS OPENED"})),
}

_PLACEHOLDER_LINES: dict[str, str] = {
    "hook": "I tried to rob every player in Steal an Egg -- here's what actually happened.",
    "goal": "The goal: six eggs, zero caught. Counter starts at zero out of six.",
    "chase": "A guard spots me immediately and the chase is on.",
    "near_miss": "That was way too close -- I almost lost it right there.",
    "fail": "And... caught. That attempt is over.",
    "strategy": "Time to change the plan before I try again.",
    "climax": "Final egg. If this works, that's six for six.",
    "payoff": "All six eggs, stolen. That's the run.",
    "egg_anticipation_1": "First Special Egg of the video -- let's see what we get.",
    "egg_reveal_1": "A common egg to start things off.",
    "egg_anticipation_2": "Second egg incoming.",
    "egg_reveal_2": "That's a rare! Already better than the first.",
    "egg_anticipation_3": "Last egg of the video. This is the one that matters.",
    "egg_reveal_3": "LEGENDARY! That is an incredible pull.",
    "comparison": "Common, rare, legendary -- three for three on getting better.",
}


def select_windows_for_target_duration(
    windows: list[tuple[float, float]], target_duration_sec: float
) -> list[tuple[float, float]]:
    """Honest, documented heuristic for the "~2h raw -> ~12m story" mode.

    No vision/engagement model is available in this environment, so this
    does NOT claim to find "the best" or "most exciting" moments -- that
    would be fabricating editorial judgment the app doesn't actually have.
    Instead: always keep the first window (the hook) and the last window
    (the payoff), then greedily add the *shortest* remaining windows first,
    on the defensible-but-explicitly-heuristic theory that a short window
    between two scene cuts means more cut frequency / more visual change
    per second than a long static window -- a real, measured signal (scene
    cuts are real), even though "short = more interesting" is a heuristic,
    not a certainty. Selected windows are returned back in chronological
    order so the story stays linear. If the raw total is already within
    budget, nothing is dropped.
    """
    if not windows:
        return []
    total = sum(e - s for s, e in windows)
    if total <= target_duration_sec or len(windows) <= 2:
        return windows

    first, last = windows[0], windows[-1]
    middle = windows[1:-1]
    middle_sorted = sorted(middle, key=lambda w: w[1] - w[0])

    kept = {first, last}
    running = (first[1] - first[0]) + (last[1] - last[0])
    for w in middle_sorted:
        dur = w[1] - w[0]
        if running + dur > target_duration_sec:
            continue
        kept.add(w)
        running += dur

    return sorted(kept, key=lambda w: w[0])


def build_rough_cut_from_scene_cuts(
    project_id: str,
    media_id: str,
    preset: AspectPreset,
    width: int,
    height: int,
    fps: float,
    total_duration_sec: float,
    windows: list[tuple[float, float]],
) -> TimelineDocument:
    """Honest fallback for real (non-annotated) footage: no vision model is
    configured in this environment, so this does NOT invent a story. It
    turns detected scene-cut windows into a neutral rough cut with generic
    per-window narration placeholders the user is expected to rewrite, and
    adds no graphics/SFX/motion -- those require either manual markers or a
    creative-brief instruction, never fabricated automatically."""
    scenes: list[Scene] = []
    beats: list[StoryBeat] = []
    narration: list[NarrationBlock] = []
    for start, end in windows:
        scene = Scene(
            media_id=media_id,
            source_in_sec=start,
            source_out_sec=end,
            evidence_kind=EvidenceKind.scene_cut_detected,
            confidence=0.5,
            reason=f"ffmpeg scene-cut window {start:.1f}s-{end:.1f}s (no story semantics inferred)",
        )
        scenes.append(scene)
        beat = StoryBeat(
            kind=StoryBeatKind.attempt,
            output_start_sec=start,
            output_end_sec=end,
            source_scene_ids=[scene.id],
            summary=f"Unlabeled scene {start:.1f}s-{end:.1f}s -- needs a manual marker or creative brief to assign a story beat.",
        )
        beats.append(beat)
        narration.append(
            NarrationBlock(
                story_beat_id=beat.id,
                text="[Add narration for this scene -- no AI vision model is configured, so nothing was inferred.]",
                output_start_sec=start + 0.1,
                duration_sec=0.0,
                grounded_in_timestamps=[start],
            )
        )

    return TimelineDocument(
        project_id=project_id,
        preset=preset,
        width=width,
        height=height,
        fps=fps,
        total_duration_sec=total_duration_sec,
        scenes=scenes,
        beats=beats,
        narration=narration,
        audio_tracks=[
            AudioTrack(kind=AudioTrackKind.voice),
            AudioTrack(kind=AudioTrackKind.sfx),
            AudioTrack(kind=AudioTrackKind.game_audio, gain_db=-6.0),
            AudioTrack(kind=AudioTrackKind.music, gain_db=-14.0),
        ],
        sound_cue_plan=SoundCuePlan(project_id=project_id),
    )


def build_timeline_from_events(
    project_id: str,
    media_id: str,
    preset: AspectPreset,
    width: int,
    height: int,
    fps: float,
    events: list[dict],
    evidence_kind: EvidenceKind = EvidenceKind.simulated_annotation,
) -> TimelineDocument:
    """events: sorted list of {at_sec, label, kind} with a trailing 'end' marker."""
    real_events = [e for e in events if e["kind"] != "end"]
    end_time = events[-1]["at_sec"]

    scenes: list[Scene] = []
    beats: list[StoryBeat] = []
    narration: list[NarrationBlock] = []
    graphics: list[GraphicLayer] = []
    motion: list[MotionPreset] = []
    cues: list[SoundCue] = []

    for i, ev in enumerate(real_events):
        start = ev["at_sec"]
        end = real_events[i + 1]["at_sec"] if i + 1 < len(real_events) else end_time
        rule = _KIND_RULES.get(ev["kind"], dict(beat=StoryBeatKind.attempt, sfx=None, motion=None, graphic=None))

        scene = Scene(
            media_id=media_id,
            source_in_sec=start,
            source_out_sec=end,
            evidence_kind=evidence_kind,
            confidence=0.95 if evidence_kind == EvidenceKind.simulated_annotation else 0.6,
            reason=f"annotated segment: {ev['label']}",
        )
        scenes.append(scene)

        beat = StoryBeat(
            kind=rule["beat"],
            output_start_sec=start,
            output_end_sec=end,
            source_scene_ids=[scene.id],
            summary=ev["label"],
        )
        beats.append(beat)

        line = _PLACEHOLDER_LINES.get(ev["kind"], ev["label"])
        narration.append(
            NarrationBlock(
                story_beat_id=beat.id,
                text=line,
                output_start_sec=start + 0.3,
                duration_sec=max(1.0, min(end - start - 0.6, 6.0)),
                grounded_in_timestamps=[start],
            )
        )

        if rule["graphic"]:
            kind, params = rule["graphic"]
            graphics.append(
                GraphicLayer(kind=kind, output_start_sec=start, output_end_sec=end, params=params)
            )

        if rule["motion"]:
            motion.append(MotionPreset(kind=rule["motion"], output_start_sec=start, output_end_sec=end))

        if rule["sfx"]:
            # Sync point = start of segment (anticipation->reveal handled by the
            # dedicated 200-500ms pre-roll in the sound-cue planner, not here).
            cues.append(
                SoundCue(
                    audio_asset_id="",  # filled in by app.audio.cues.assign_assets
                    category=rule["sfx"],
                    output_start_ms=int(start * 1000),
                    duration_ms=600,
                    trigger_source=evidence_kind,
                    source_timestamp_sec=start,
                    evidence=f"segment '{ev['label']}' at {start}s",
                    confidence=scene.confidence,
                )
            )

    return TimelineDocument(
        project_id=project_id,
        preset=preset,
        width=width,
        height=height,
        fps=fps,
        total_duration_sec=end_time,
        scenes=scenes,
        beats=beats,
        narration=narration,
        graphics=graphics,
        motion=motion,
        audio_tracks=[
            AudioTrack(kind=AudioTrackKind.voice),
            AudioTrack(kind=AudioTrackKind.sfx),
            AudioTrack(kind=AudioTrackKind.game_audio, gain_db=-6.0),
            AudioTrack(kind=AudioTrackKind.music, gain_db=-14.0),
        ],
        sound_cue_plan=SoundCuePlan(project_id=project_id, cues=cues),
    )
