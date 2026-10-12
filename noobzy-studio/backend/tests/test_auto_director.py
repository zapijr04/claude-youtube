from app.schemas import AspectPreset, MotionPresetKind, SoundCueCategory
from app.timeline.builder import (
    apply_generic_auto_director,
    build_rough_cut_from_scene_cuts,
    distribute_script_across_scenes,
)


def _windows():
    # durations [8, 10, 3, 24, 5], mean=10: the 3s scene is well under the
    # 0.6x-mean shake threshold, the 24s scene well over the 1.4x-mean zoom
    # threshold -- deterministically exercises both heuristics.
    return [(0.0, 8.0), (8.0, 18.0), (18.0, 21.0), (21.0, 45.0), (45.0, 50.0)]


def test_auto_director_adds_transitions_and_duration_keyed_motion():
    tl = build_rough_cut_from_scene_cuts(
        "p", "m", AspectPreset.LONG_FORM_STORY, 1920, 1080, 30.0, 50.0, _windows(),
        auto_style=True,
    )
    # one TRANSITION cue per internal boundary (not before the very first scene)
    assert len(tl.sound_cue_plan.cues) == len(_windows()) - 1
    assert all(c.category == SoundCueCategory.TRANSITION for c in tl.sound_cue_plan.cues)
    for c in tl.sound_cue_plan.cues:
        assert c.evidence  # every auto cue cites the real cut it's grounded in

    kinds = {m.kind for m in tl.motion}
    assert MotionPresetKind.shake in kinds  # the 6s scene is well below the mean
    assert MotionPresetKind.zoom in kinds   # the 18s scene is well above the mean


def test_auto_style_false_adds_nothing():
    tl = build_rough_cut_from_scene_cuts(
        "p", "m", AspectPreset.LONG_FORM_STORY, 1920, 1080, 30.0, 50.0, _windows(),
        auto_style=False,
    )
    assert tl.motion == []
    assert tl.sound_cue_plan.cues == []


def test_distribute_script_is_proportional_to_scene_duration():
    windows = [(0.0, 2.0), (2.0, 20.0)]  # second scene is 9x longer
    from app.schemas import EvidenceKind, Scene

    scenes = [
        Scene(media_id="m", source_in_sec=s, source_out_sec=e, evidence_kind=EvidenceKind.scene_cut_detected)
        for s, e in windows
    ]
    script = " ".join([f"Sentence number {i}." for i in range(10)])
    assigned = distribute_script_across_scenes(script, scenes)
    first_count = len(assigned.get(scenes[0].id, "").split(".")) - 1
    second_count = len(assigned.get(scenes[1].id, "").split(".")) - 1
    assert second_count > first_count  # the much longer scene gets more of the script


def test_narration_script_grounds_real_scene_text_and_leaves_rest_as_placeholder():
    windows = _windows()
    script = "First real line here. Second real line here."
    tl = build_rough_cut_from_scene_cuts(
        "p", "m", AspectPreset.LONG_FORM_STORY, 1920, 1080, 30.0, 50.0, windows,
        narration_script=script, auto_style=False,
    )
    texts = [nb.text for nb in tl.narration]
    assert any("First real line" in t or "Second real line" in t for t in texts)
    assert any(t.startswith("[Add narration") for t in texts)  # not every scene can get a sentence
    for nb in tl.narration:
        assert nb.grounded_in_timestamps  # every block still cites a real timestamp
