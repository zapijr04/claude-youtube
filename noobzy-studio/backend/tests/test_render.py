import subprocess
from pathlib import Path

import numpy as np
import pytest

from app.audio import cues, mix, sfx_library, tts
from app.media import ffprobe_util
from app.render import ffmpeg_render
from app.render.overlays import make_cutout_png
from app.schemas import AspectPreset
from app.timeline.builder import build_timeline_from_events


def _grab_frame_stddev(video_path, t: float, crop: str, size: tuple[int, int] = (500, 100)) -> float:
    """Spatial standard deviation (over pixels, in grayscale) of a cropped
    region at time t -- a real, frame-time proof that *something*
    (text/graphics) was drawn there, vs a flat background with ~0 stddev.
    Must convert to per-pixel luma first: std() over raw interleaved RGB
    bytes conflates R/G/B channel differences with spatial detail, giving a
    high "variance" even for a perfectly flat color."""
    w, h = size
    cmd = [
        "ffmpeg", "-ss", f"{t:.3f}", "-i", str(video_path),
        "-vf", crop, "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "-",
    ]
    result = subprocess.run(cmd, capture_output=True)
    arr = np.frombuffer(result.stdout, dtype=np.uint8)
    if arr.size < w * h * 3:
        return 0.0
    rgb = arr[: w * h * 3].reshape(h, w, 3).astype(np.float32)
    luma = rgb[..., 0] * 0.299 + rgb[..., 1] * 0.587 + rgb[..., 2] * 0.114
    return float(luma.std())


@pytest.fixture(scope="module")
def rendered_long(tmp_path_factory, long_fixture):
    work = tmp_path_factory.mktemp("render_long")
    tl = build_timeline_from_events(
        "p_long", "m_long", AspectPreset.LONG_FORM_STORY, 1920, 1080, 30.0, long_fixture["events"]
    )
    for nb in tl.narration:
        tts.synthesize_local_fallback(nb, work / "vo")
    captions = ffmpeg_render.select_kinetic_caption_words(tl.narration)

    assets = sfx_library.build_and_register_library(work / "sfx")
    asset_ids = {a.name: a.id for a in assets}
    asset_paths = {a.id: a.file_path for a in assets}
    music_asset = sfx_library.build_music_loop(work / "music.wav", duration_s=20)
    asset_paths[music_asset.id] = music_asset.file_path
    plan = cues.assign_assets(tl.sound_cue_plan, asset_ids, density="balanced")

    sfx_items = [(asset_paths[c.audio_asset_id], c.output_start_ms, c.gain_db) for c in plan.cues]
    sfx_track = mix.place_sounds_on_track(sfx_items, tl.total_duration_sec, work / "sfx_bus.wav")
    vo_items = [(nb.audio_path, int(nb.output_start_sec * 1000), 0.0) for nb in tl.narration]
    voice_track = mix.place_sounds_on_track(vo_items, tl.total_duration_sec, work / "voice_bus.wav")
    game_track = mix.extract_game_audio(long_fixture["path"], tl.total_duration_sec, work / "game_bus.wav")
    music_track = mix.loop_music(music_asset.file_path, tl.total_duration_sec, work / "music_raw.wav")
    ducked = mix.duck_against_voice(music_track, voice_track, work / "music_ducked.wav")
    final_raw = mix.mix_stems([voice_track, sfx_track, game_track, ducked], work / "final_raw.wav")
    final_audio = mix.normalize_to_target(final_raw, work / "final.wav")

    cutout_png = make_cutout_png(work / "cutout.png")
    out = ffmpeg_render.render(
        media_path=long_fixture["path"], scenes=tl.scenes, motions=tl.motion, graphics=tl.graphics,
        captions=captions, cutout_png=cutout_png, final_audio_path=final_audio,
        out_path=work / "long.mp4", preset=AspectPreset.LONG_FORM_STORY,
    )
    return {"video": out, "timeline": tl, "captions": captions, "audio": final_audio, "work": work}


def test_long_form_render_is_valid_16x9_mp4(rendered_long, long_fixture):
    info = ffprobe_util.probe(rendered_long["video"])
    assert info["width"] == 1920 and info["height"] == 1080
    assert abs(info["duration_sec"] - long_fixture["total_duration_sec"]) < 1.0
    assert info["has_audio"]


def test_long_form_counter_graphic_appears_only_in_its_window(rendered_long):
    goal_layer = next(g for g in rendered_long["timeline"].graphics if g.params.get("value") == "0/6")
    mid = (goal_layer.output_start_sec + goal_layer.output_end_sec) / 2
    crop = "crop=500:100:1380:30"  # top-right counter box region
    during = _grab_frame_stddev(rendered_long["video"], mid, crop)
    before = _grab_frame_stddev(rendered_long["video"], max(0, goal_layer.output_start_sec - 2), crop)
    assert during > before + 5, "counter graphic should visibly change pixels only inside its time window"


def test_long_form_sfx_cues_are_audible_in_final_mix(rendered_long):
    plan = rendered_long["timeline"].sound_cue_plan
    audible_count = 0
    for c in plan.cues:
        start_s = c.output_start_ms / 1000.0
        rms = mix.measure_rms_db(rendered_long["audio"], max(0, start_s - 0.05), start_s + 0.5)
        if rms > -50.0:
            audible_count += 1
    assert audible_count >= 4


@pytest.fixture(scope="module")
def rendered_short(tmp_path_factory, short_fixture):
    work = tmp_path_factory.mktemp("render_short")
    tl = build_timeline_from_events(
        "p_short", "m_short", AspectPreset.SHORT_EGG_REVEAL, 1920, 1080, 30.0, short_fixture["events"]
    )
    for nb in tl.narration:
        tts.synthesize_local_fallback(nb, work / "vo")
    captions = ffmpeg_render.select_kinetic_caption_words(tl.narration)
    assets = sfx_library.build_and_register_library(work / "sfx")
    asset_ids = {a.name: a.id for a in assets}
    asset_paths = {a.id: a.file_path for a in assets}
    music_asset = sfx_library.build_music_loop(work / "music.wav", duration_s=15)
    asset_paths[music_asset.id] = music_asset.file_path
    plan = cues.assign_assets(tl.sound_cue_plan, asset_ids, density="high-energy")

    sfx_items = [(asset_paths[c.audio_asset_id], c.output_start_ms, c.gain_db) for c in plan.cues]
    sfx_track = mix.place_sounds_on_track(sfx_items, tl.total_duration_sec, work / "sfx_bus.wav")
    vo_items = [(nb.audio_path, int(nb.output_start_sec * 1000), 0.0) for nb in tl.narration]
    voice_track = mix.place_sounds_on_track(vo_items, tl.total_duration_sec, work / "voice_bus.wav")
    game_track = mix.extract_game_audio(short_fixture["path"], tl.total_duration_sec, work / "game_bus.wav")
    music_track = mix.loop_music(music_asset.file_path, tl.total_duration_sec, work / "music_raw.wav")
    ducked = mix.duck_against_voice(music_track, voice_track, work / "music_ducked.wav")
    final_raw = mix.mix_stems([voice_track, sfx_track, game_track, ducked], work / "final_raw.wav")
    final_audio = mix.normalize_to_target(final_raw, work / "final.wav")
    cutout_png = make_cutout_png(work / "cutout.png")
    out = ffmpeg_render.render(
        media_path=short_fixture["path"], scenes=tl.scenes, motions=tl.motion, graphics=tl.graphics,
        captions=captions, cutout_png=cutout_png, final_audio_path=final_audio,
        out_path=work / "short.mp4", preset=AspectPreset.SHORT_EGG_REVEAL,
    )
    return {"video": out, "timeline": tl, "plan": plan}


def test_short_form_render_is_valid_vertical_mp4(rendered_short, short_fixture):
    info = ffprobe_util.probe(rendered_short["video"])
    assert info["width"] == 1080 and info["height"] == 1920
    assert abs(info["duration_sec"] - short_fixture["total_duration_sec"]) < 1.0


def test_short_form_has_three_egg_events_with_sfx(rendered_short):
    categories = [c.category.value for c in rendered_short["plan"].cues]
    assert categories.count("EGG_OPEN") >= 2  # two common/rare reveals
    assert "BIG_REVEAL" in categories  # legendary reveal


def test_render_fails_loudly_on_missing_media(tmp_path, long_fixture):
    tl = build_timeline_from_events(
        "p", "m", AspectPreset.LONG_FORM_STORY, 1920, 1080, 30.0, long_fixture["events"]
    )
    cutout_png = make_cutout_png(tmp_path / "cutout.png")
    silence = tmp_path / "silence.wav"
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc", "-t", "1", str(silence)],
        check=True, capture_output=True,
    )
    with pytest.raises(RuntimeError):
        ffmpeg_render.render(
            media_path=tmp_path / "does_not_exist.mp4", scenes=tl.scenes, motions=[], graphics=[],
            captions=[], cutout_png=cutout_png, final_audio_path=silence,
            out_path=tmp_path / "out.mp4", preset=AspectPreset.LONG_FORM_STORY,
        )
