from app.schemas import AspectPreset, EvidenceKind
from app.timeline.builder import build_rough_cut_from_scene_cuts, build_timeline_from_events


def test_build_from_simulated_events_grounds_every_beat(long_fixture):
    tl = build_timeline_from_events(
        "proj1", "media1", AspectPreset.LONG_FORM_STORY, 1920, 1080, 30.0, long_fixture["events"]
    )
    assert len(tl.scenes) == 8
    assert tl.total_duration_sec == long_fixture["total_duration_sec"]
    for scene in tl.scenes:
        assert scene.evidence_kind == EvidenceKind.simulated_annotation
    for nb in tl.narration:
        assert nb.grounded_in_timestamps, "every narration block must cite a source timestamp"
    assert tl.sound_cue_plan.cues, "story beats should propose sound cues"


def test_build_rough_cut_never_invents_graphics_or_semantic_sfx_with_auto_style_off():
    windows = [(0.0, 5.0), (5.0, 12.0), (12.0, 20.0)]
    tl = build_rough_cut_from_scene_cuts(
        "proj2", "media2", AspectPreset.LONG_FORM_STORY, 1920, 1080, 30.0, 20.0, windows,
        auto_style=False,
    )
    assert len(tl.scenes) == 3
    assert tl.graphics == []
    assert tl.motion == []
    assert tl.sound_cue_plan.cues == []
    for scene in tl.scenes:
        assert scene.evidence_kind == EvidenceKind.scene_cut_detected
        assert scene.confidence <= 0.5


def test_build_rough_cut_default_adds_generic_style_but_never_graphics():
    # auto_style defaults to True: a plain upload-and-go flow still gets
    # generic, non-fabricated editorial rhythm (see test_auto_director.py
    # for the detailed behavior) -- but graphics (counters, cards) require
    # real data this path doesn't have, so those stay empty regardless.
    windows = [(0.0, 5.0), (5.0, 12.0), (12.0, 20.0)]
    tl = build_rough_cut_from_scene_cuts(
        "proj3", "media3", AspectPreset.LONG_FORM_STORY, 1920, 1080, 30.0, 20.0, windows
    )
    assert tl.graphics == []
    assert tl.sound_cue_plan.cues, "auto_style defaults on, so transition cues are expected"
