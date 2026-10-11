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


def test_build_rough_cut_never_invents_graphics_or_sfx():
    windows = [(0.0, 5.0), (5.0, 12.0), (12.0, 20.0)]
    tl = build_rough_cut_from_scene_cuts(
        "proj2", "media2", AspectPreset.LONG_FORM_STORY, 1920, 1080, 30.0, 20.0, windows
    )
    assert len(tl.scenes) == 3
    assert tl.graphics == []
    assert tl.motion == []
    assert tl.sound_cue_plan.cues == []
    for scene in tl.scenes:
        assert scene.evidence_kind == EvidenceKind.scene_cut_detected
        assert scene.confidence <= 0.5
