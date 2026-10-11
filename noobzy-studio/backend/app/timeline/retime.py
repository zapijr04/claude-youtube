"""Non-destructive retiming operations on a TimelineDocument.

Two real operations that both need the same underlying move: shifting
every downstream beat/narration/graphic/motion/sound-cue timestamp so
synchronization never drifts after a local change.

1. `shift_after` -- used when regenerating one ElevenLabs/local-fallback
   narration block changes its duration: if the new block now overlaps the
   next one, every beat/narration/graphic/motion/cue at or after that point
   is pushed back by the overflow, and total_duration_sec grows to match.
   (If the new block is shorter, this also *pulls in* everything after it
   so the cut doesn't gain a dead gap -- shift_after accepts a negative
   delta too.)

2. `apply_speed_ramp` -- sets a Scene's playback_rate and retimes
   everything after it so the output timeline stays internally consistent
   (the sped-up/slowed-down scene's output duration actually changes;
   nothing downstream is left pointing at the old timestamps).
"""
from __future__ import annotations

from app.schemas import Scene, TimelineDocument


def _shift(value: float, from_sec: float, delta_sec: float) -> float:
    return value + delta_sec if value >= from_sec - 1e-6 else value


def shift_after(timeline: TimelineDocument, from_sec: float, delta_sec: float, exclude_narration_id: str | None = None) -> TimelineDocument:
    if abs(delta_sec) < 1e-6:
        return timeline

    for beat in timeline.beats:
        beat.output_start_sec = _shift(beat.output_start_sec, from_sec, delta_sec)
        beat.output_end_sec = _shift(beat.output_end_sec, from_sec, delta_sec)

    for nb in timeline.narration:
        if nb.id == exclude_narration_id:
            continue
        nb.output_start_sec = _shift(nb.output_start_sec, from_sec, delta_sec)

    for g in timeline.graphics:
        g.output_start_sec = _shift(g.output_start_sec, from_sec, delta_sec)
        g.output_end_sec = _shift(g.output_end_sec, from_sec, delta_sec)

    for m in timeline.motion:
        m.output_start_sec = _shift(m.output_start_sec, from_sec, delta_sec)
        m.output_end_sec = _shift(m.output_end_sec, from_sec, delta_sec)

    if timeline.sound_cue_plan:
        from_ms = from_sec * 1000
        delta_ms = delta_sec * 1000
        for c in timeline.sound_cue_plan.cues:
            if c.output_start_ms >= from_ms - 1:
                c.output_start_ms = max(0, int(c.output_start_ms + delta_ms))
            if c.source_timestamp_sec is not None:
                c.source_timestamp_sec = _shift(c.source_timestamp_sec, from_sec, delta_sec)

    # total_duration_sec genuinely shrinks when delta_sec is negative (a
    # speed-up, or a narration block that got shorter on regeneration) --
    # an earlier version wrongly max()'d this against the old value, which
    # silently blocked shrinking. Caught by this exact scenario failing.
    timeline.total_duration_sec = max(0.0, timeline.total_duration_sec + delta_sec)
    return timeline


def resync_after_narration_change(timeline: TimelineDocument, changed_block_id: str) -> TimelineDocument:
    """Call after a NarrationBlock's audio/duration changed (regeneration).
    If the block now runs long enough to collide with whatever comes next
    on the narration track, push everything from that point on back by the
    overflow; if it got shorter, pull everything in to close the gap.
    Either way, every downstream SFX cue / caption / graphic stays in sync
    because they're all retimed by the same delta."""
    narration_sorted = sorted(timeline.narration, key=lambda n: n.output_start_sec)
    changed = next((n for n in narration_sorted if n.id == changed_block_id), None)
    if changed is None:
        return timeline

    idx = narration_sorted.index(changed)
    changed_end = changed.output_start_sec + changed.duration_sec

    if idx + 1 < len(narration_sorted):
        next_block = narration_sorted[idx + 1]
        delta = changed_end - next_block.output_start_sec
        if abs(delta) > 1e-3:
            shift_after(timeline, next_block.output_start_sec, delta, exclude_narration_id=changed.id)
    else:
        # last block: just make sure total duration covers it
        timeline.total_duration_sec = max(timeline.total_duration_sec, changed_end)

    return timeline


def apply_speed_ramp(timeline: TimelineDocument, scene_id: str, rate: float) -> TimelineDocument:
    """Sets scene.playback_rate = rate and retimes everything after this
    scene's current output position so the whole document stays
    internally consistent. rate > 1 = sped up (output gets shorter),
    rate < 1 = slow motion (output gets longer)."""
    if rate <= 0:
        raise ValueError("playback_rate must be > 0")

    scenes_sorted = sorted(timeline.scenes, key=lambda s: s.source_in_sec)
    # Scenes don't carry their own output position explicitly -- they're
    # concatenated in order, so the scene's output start is the sum of the
    # (rate-adjusted) durations of every scene before it.
    output_cursor = 0.0
    target: Scene | None = None
    for s in scenes_sorted:
        if s.id == scene_id:
            target = s
            break
        output_cursor += (s.source_out_sec - s.source_in_sec) / s.playback_rate

    if target is None:
        raise ValueError(f"scene {scene_id} not found in timeline")

    old_output_duration = (target.source_out_sec - target.source_in_sec) / target.playback_rate
    new_output_duration = (target.source_out_sec - target.source_in_sec) / rate
    delta = new_output_duration - old_output_duration

    target.playback_rate = rate
    shift_point = output_cursor + old_output_duration
    if abs(delta) > 1e-6:
        shift_after(timeline, shift_point, delta)
    return timeline
