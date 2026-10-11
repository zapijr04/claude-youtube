"""The one real render pipeline, shared by /preview and /export/final-video.

Point 6 (non-negotiable) of the product spec: editing a project (cuts,
captions, ElevenLabs narration, SFX, motion graphics, mixing, fixes) must
happen entirely against the persisted TimelineDocument (see app.db's
timeline_versions history) and MUST NOT write a new "finished" MP4 to disk
on every edit. Only an explicit Export Final Video action may do that.

This module is the single place that turns a TimelineDocument + SourceMedia
into actual audio/video files, parameterized by `quality`:

  - "preview": fast encode settings, written under a managed, content-hash
    keyed CACHE directory that gets reused across repeated calls with an
    unchanged timeline (and pruned so stale previews don't pile up). This
    is what the Editor's live/fast preview calls.
  - "final": full-quality encode, written to a TEMP file first, QC'd
    (ffprobe + loudness/clipping check), and only then atomically moved
    into the caller-chosen output path. This is the only code path that
    may place a file under a project's "final export" output directory.

Both quality tiers run the exact same real pipeline (ElevenLabs or local
fallback narration, procedural SFX with real pitch/speed, multi-bus mix
with measured ducking, FFmpeg render) -- "preview" is not a fake stand-in,
it is a faster encode of the same timeline.
"""
from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

from app import db
from app.audio import cues as cues_mod
from app.audio import mix, sfx_library, tts
from app.export import otio_export, srt_export
from app.media.ffprobe_util import probe as ffprobe
from app.render import ffmpeg_render
from app.render.overlays import make_cutout_png
from app.schemas import AspectPreset, TimelineDocument


def timeline_content_hash(timeline: TimelineDocument, media_id: str, sfx_density: str) -> str:
    """Stable hash of everything that affects the rendered output, used to
    decide whether a cached preview can be reused instead of re-rendered."""
    payload = timeline.model_dump_json(exclude={"id", "created_at", "updated_at"})
    h = hashlib.sha256()
    h.update(payload.encode())
    h.update(media_id.encode())
    h.update(sfx_density.encode())
    return h.hexdigest()[:20]


def _build_audio_and_video(
    timeline: TimelineDocument,
    media: dict,
    work_dir: Path,
    out_video_path: Path,
    sfx_density: str,
    fast: bool,
) -> dict:
    work_dir.mkdir(parents=True, exist_ok=True)

    for nb in timeline.narration:
        if nb.duration_sec <= 0:
            nb.duration_sec = tts.estimate_duration_sec(nb.text)
        if nb.audio_path and Path(nb.audio_path).exists():
            continue  # already synthesized (e.g. only a later block changed)
        try:
            tts.synthesize_elevenlabs(nb, work_dir / "vo")
        except tts.ElevenLabsNotConfigured:
            tts.synthesize_local_fallback(nb, work_dir / "vo")

    captions = ffmpeg_render.select_kinetic_caption_words(timeline.narration)

    assets = sfx_library.build_and_register_library(work_dir / "sfx")
    for a in assets:
        db.upsert_audio_asset(a)
    asset_ids = {a.name: a.id for a in assets}
    asset_paths = {a.id: a.file_path for a in assets}
    music_asset = sfx_library.build_music_loop(work_dir / "music" / "signature.wav", duration_s=20)
    db.upsert_audio_asset(music_asset)
    asset_paths[music_asset.id] = music_asset.file_path

    if timeline.sound_cue_plan:
        cues_mod.assign_assets(timeline.sound_cue_plan, asset_ids, density=sfx_density)
        sfx_cues = timeline.sound_cue_plan.cues
    else:
        sfx_cues = []

    sfx_track = mix.place_cues_on_track(sfx_cues, asset_paths, timeline.total_duration_sec, work_dir / "sfx_bus.wav")
    vo_items = [
        (nb.audio_path, int(nb.output_start_sec * 1000), 0.0)
        for nb in timeline.narration if nb.audio_path
    ]
    voice_track = mix.place_sounds_on_track(vo_items, timeline.total_duration_sec, work_dir / "voice_bus.wav")
    game_track = mix.extract_game_audio(media["path"], timeline.total_duration_sec, work_dir / "game_bus.wav")
    music_track = mix.loop_music(music_asset.file_path, timeline.total_duration_sec, work_dir / "music_bus_raw.wav")
    ducked = mix.duck_against_voice(music_track, voice_track, work_dir / "music_bus_ducked.wav")
    final_raw = mix.mix_stems([voice_track, sfx_track, game_track, ducked], work_dir / "final_mix_raw.wav")
    final_audio = mix.normalize_to_target(
        final_raw, work_dir / "final_mix.wav", target_lufs=timeline.target_lufs
    )

    cutout_png = make_cutout_png(work_dir / "cutout.png")
    out_video_path.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg_render.render(
        media_path=media["path"],
        scenes=timeline.scenes,
        motions=timeline.motion,
        graphics=timeline.graphics,
        captions=captions,
        cutout_png=cutout_png,
        final_audio_path=final_audio,
        out_path=out_video_path,
        preset=timeline.preset,
        width=media["width"],
        height=media["height"],
        fps=media["fps"],
        fast=fast,
    )

    loudness = mix.loudness_report(final_audio)
    gap_report = mix.voice_coverage_gap_report(voice_track, timeline.total_duration_sec)

    return {
        "video_path": str(out_video_path),
        "audio_mix_path": final_audio,
        "stems": {
            "voice": voice_track,
            "sfx": sfx_track,
            "game": game_track,
            "music_ducked": ducked,
        },
        "loudness_report": loudness,
        "voice_coverage_report": gap_report,
        "sfx_cues_rendered": len(sfx_cues),
    }


def render_preview(
    timeline: TimelineDocument, media: dict, cache_dir: Path, sfx_density: str = "balanced"
) -> dict:
    """Fast, cache-reused preview. Writes ONLY under cache_dir (never the
    project's chosen final-export output directory)."""
    content_hash = timeline_content_hash(timeline, media["id"], sfx_density)
    preview_dir = cache_dir / "preview"
    out_video = preview_dir / f"preview_{content_hash}.mp4"

    if out_video.exists():
        return {
            "video_path": str(out_video),
            "cached": True,
            "content_hash": content_hash,
        }

    # Prune older previews for this project before building the new one --
    # "reuse and clean them", never let the cache grow unbounded.
    if preview_dir.exists():
        for old in preview_dir.glob("preview_*.mp4"):
            old.unlink(missing_ok=True)

    work_dir = cache_dir / "work"
    result = _build_audio_and_video(timeline, media, work_dir, out_video, sfx_density, fast=True)
    result["cached"] = False
    result["content_hash"] = content_hash
    return result


def render_final_export(
    timeline: TimelineDocument,
    media: dict,
    cache_dir: Path,
    output_dir: Path,
    filename: str,
    sfx_density: str = "balanced",
) -> dict:
    """The ONLY function allowed to write into a project's chosen output
    directory. Renders full quality to a temp file inside cache_dir, QCs
    it for real (ffprobe + loudness/clipping), then atomically finalizes
    by moving it into place -- so output_dir never contains a partial or
    unverified file."""
    work_dir = cache_dir / "export_work"
    tmp_video = cache_dir / "export_tmp" / f"tmp_{filename}"
    if tmp_video.exists():
        tmp_video.unlink()

    result = _build_audio_and_video(timeline, media, work_dir, tmp_video, sfx_density, fast=False)

    # Real QC gate before the file is allowed to become "the" export.
    info = ffprobe(tmp_video)
    qc_errors = []
    if not info["has_audio"]:
        qc_errors.append("rendered file has no audio stream")
    if info["duration_sec"] <= 0:
        qc_errors.append("rendered file has zero duration")
    if result["loudness_report"].get("clipping_detected"):
        qc_errors.append("clipping detected in final mix")
    if qc_errors:
        raise RuntimeError(f"Final export failed QC, not finalized: {'; '.join(qc_errors)}")

    output_dir.mkdir(parents=True, exist_ok=True)
    final_path = output_dir / filename
    shutil.move(str(tmp_video), str(final_path))  # atomic within same filesystem, safe fallback across devices
    result["video_path"] = str(final_path)
    result["qc_passed"] = True
    result["probe"] = info

    # Audio stems alongside the one finished MP4 -- part of the spec's
    # delivery bundle (point 5), copied (not moved) from the cache so the
    # cache keeps its own copy for any later re-export.
    stems_dir = output_dir / f"{Path(filename).stem}_stems"
    stems_dir.mkdir(parents=True, exist_ok=True)
    result["stems"] = {
        name: str(shutil.copy(src, stems_dir / f"{name}.wav")) for name, src in result["stems"].items()
    }
    return result


def export_sidecars(timeline: TimelineDocument, media_path: str, output_dir: Path, base_name: str) -> dict:
    """OTIO/FCPXML/SRT/timeline.json -- also only written as part of the
    explicit final-export action, alongside the one MP4."""
    output_dir.mkdir(parents=True, exist_ok=True)
    captions = ffmpeg_render.select_kinetic_caption_words(timeline.narration)
    timeline_json_path = output_dir / f"{base_name}.timeline.json"
    timeline_json_path.write_text(timeline.model_dump_json(indent=2))
    return {
        "timeline_json": str(timeline_json_path),
        "otio": otio_export.export_otio(timeline, media_path, output_dir / f"{base_name}.otio"),
        "fcpxml": otio_export.export_fcpxml(timeline, media_path, output_dir / f"{base_name}.fcpxml"),
        "srt_full": srt_export.export_full_srt(timeline.narration, output_dir / f"{base_name}.full.srt"),
        "srt_selective": srt_export.export_selective_srt(captions, output_dir / f"{base_name}.selective.srt"),
    }
