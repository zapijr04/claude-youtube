import wave
from pathlib import Path

import numpy as np

from app.audio import cues, mix, sfx, sfx_library, tts
from app.schemas import AspectPreset, NarrationBlock
from app.timeline.builder import build_timeline_from_events


def _is_audible(wav_path: str, min_rms: float = -45.0) -> bool:
    rms = mix.measure_rms_db(wav_path)
    return rms > min_rms


def test_every_procedural_sfx_is_real_audio_not_silence(tmp_path):
    paths = sfx.render_all(tmp_path)
    assert len(paths) >= 13
    for name, path in paths.items():
        with wave.open(path) as w:
            assert w.getnframes() > 0
        assert _is_audible(path), f"{name} should not be silent"


def test_sfx_cue_planner_expands_at_least_four_distinct_audible_cues(tmp_path, long_fixture):
    tl = build_timeline_from_events(
        "p", "m", AspectPreset.LONG_FORM_STORY, 1920, 1080, 30.0, long_fixture["events"]
    )
    assets = sfx_library.build_and_register_library(tmp_path / "sfx")
    asset_ids = {a.name: a.id for a in assets}
    asset_paths = {a.id: a.file_path for a in assets}
    plan = cues.assign_assets(tl.sound_cue_plan, asset_ids, density="balanced")
    assert len(plan.cues) >= 4

    items = [(asset_paths[c.audio_asset_id], c.output_start_ms, c.gain_db) for c in plan.cues]
    track = mix.place_sounds_on_track(items, tl.total_duration_sec, tmp_path / "sfx_bus.wav")
    for c in plan.cues:
        start_s = c.output_start_ms / 1000.0
        end_s = start_s + max(c.duration_ms, 300) / 1000.0
        rms = mix.measure_rms_db(track, max(0, start_s - 0.05), min(tl.total_duration_sec, end_s))
        assert rms > -50.0, f"cue at {start_s}s ({c.category.value}) should be audible in the mixed bus"


def test_music_ducks_measurably_under_narration(tmp_path):
    nb = NarrationBlock(text="This is a real sentence used to trigger ducking in the test.", output_start_sec=1.0)
    tts.synthesize_local_fallback(nb, tmp_path / "vo")

    music_asset = sfx_library.build_music_loop(tmp_path / "music.wav", duration_s=10)
    total = 10.0
    music_track = mix.loop_music(music_asset.file_path, total, tmp_path / "music_raw.wav")
    voice_track = mix.place_sounds_on_track(
        [(nb.audio_path, int(nb.output_start_sec * 1000), 0.0)], total, tmp_path / "voice.wav"
    )
    ducked = mix.duck_against_voice(music_track, voice_track, tmp_path / "music_ducked.wav")

    rms_before = mix.measure_rms_db(music_track, nb.output_start_sec, nb.output_start_sec + nb.duration_sec)
    rms_after = mix.measure_rms_db(ducked, nb.output_start_sec, nb.output_start_sec + nb.duration_sec)
    assert rms_after < rms_before - 6.0, "ducked music must be measurably quieter under the voice window"


def test_loudness_report_hits_target_and_detects_no_clipping(tmp_path):
    music_asset = sfx_library.build_music_loop(tmp_path / "music.wav", duration_s=5)
    normalized = mix.normalize_to_target(music_asset.file_path, tmp_path / "norm.wav", target_lufs=-14.0)
    report = mix.loudness_report(normalized)
    assert report["clipping_detected"] is False
    assert abs(report["integrated_lufs"] - (-14.0)) < 1.5
