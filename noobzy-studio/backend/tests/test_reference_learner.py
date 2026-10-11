from app.learning.reference_learner import analyze_reference_video, propose_skill_from_reference


def test_analyze_reference_video_measures_real_pacing(long_fixture):
    analysis = analyze_reference_video(long_fixture["path"])
    assert analysis["source_duration_sec"] == 75.0
    assert analysis["shot_count"] >= 5  # real scene-cut detection, not guessed
    assert analysis["avg_shot_length_sec"] > 0
    assert analysis["cuts_per_minute"] > 0


def test_propose_skill_is_staged_disabled_and_flags_non_inferable(tmp_path, long_fixture):
    manifest, profile, analysis = propose_skill_from_reference(
        long_fixture["path"], "noobzy-test-learned", "Test Learned Style"
    )
    assert manifest.enabled is False  # requires explicit approval, same as any imported skill
    assert manifest.provenance == "reference_video_learned"
    assert manifest.allowed_parameters["measured_avg_shot_length_sec"] > 0
    assert profile.needs_manual_recipe is True
    assert "FFmpeg scene-cut detection" in profile.confidence_notes
