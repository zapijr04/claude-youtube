"""NOOBZY AI STUDIO backend -- FastAPI app wiring every module together.

Run: uvicorn app.main:app --reload --port 8077
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app import db
from app.audio import cues, mix, sfx_library, tts
from app.compute import providers as compute_providers
from app.creative_brief import parse_intent
from app.export import otio_export, srt_export
from app.media import ffprobe_util, proxy, scenes as scenes_mod
from app.memory import store as memory_store
from app.render import ffmpeg_render
from app.render.overlays import make_cutout_png
from app.schemas import (
    AspectPreset,
    MemoryRecordKind,
    Project,
    ProjectStatus,
    SourceMedia,
    TimelineDocument,
)
from app.skills import loader as skills_loader
from app.skills.seed_data import SKILLS
from app.timeline.builder import build_rough_cut_from_scene_cuts

DATA_DIR = Path(db.DATA_DIR)
MEDIA_DIR = DATA_DIR / "media"
SKILLS_LIBRARY_DIR = Path(__file__).resolve().parent.parent.parent / "skills_library"

app = FastAPI(title="NOOBZY AI STUDIO API", version="0.1.0")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)


@app.on_event("startup")
def on_startup() -> None:
    db.init_db()
    if not any(SKILLS_LIBRARY_DIR.glob("*/SKILL.md")):
        skills_loader.seed_builtin_skills(SKILLS_LIBRARY_DIR, SKILLS)
    manifests = skills_loader.load_all_from_dir(SKILLS_LIBRARY_DIR)
    skills_loader.persist_all(manifests)


# ---- projects ----


class CreateProjectRequest(BaseModel):
    name: str
    preset: AspectPreset
    target_duration_sec: float = 420.0


@app.post("/projects")
def create_project(req: CreateProjectRequest) -> dict:
    project = Project(name=req.name, preset=req.preset, target_duration_sec=req.target_duration_sec)
    db.upsert_project(project)
    return json.loads(db.get_project(project.id))


@app.get("/projects")
def list_projects() -> list[dict]:
    return [json.loads(p) for p in db.list_projects()]


@app.get("/projects/{project_id}")
def get_project(project_id: str) -> dict:
    data = db.get_project(project_id)
    if not data:
        raise HTTPException(404, "project not found")
    return json.loads(data)


# ---- media import & analysis ----


@app.post("/projects/{project_id}/media")
async def import_media(project_id: str, file: UploadFile) -> dict:
    project_raw = db.get_project(project_id)
    if not project_raw:
        raise HTTPException(404, "project not found")

    dest_dir = MEDIA_DIR / project_id
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_dir / file.filename
    with dest_path.open("wb") as f:
        shutil.copyfileobj(file.file, f)

    try:
        info = ffprobe_util.probe(dest_path)
    except ffprobe_util.ProbeError as e:
        raise HTTPException(400, str(e))

    media = SourceMedia(project_id=project_id, path=str(dest_path), **info)
    thumbs_dir = dest_dir / f"{media.id}_thumbs"
    media.thumbnails = proxy.generate_thumbnails(dest_path, thumbs_dir, count=5, duration_sec=info["duration_sec"])
    media.waveform_path = proxy.generate_waveform(dest_path, dest_dir / f"{media.id}_waveform.png")
    db.upsert_source_media(media)

    project = Project.model_validate_json(project_raw)
    project.status = ProjectStatus.analyzing
    db.upsert_project(project)
    return json.loads(media.model_dump_json())


@app.post("/projects/{project_id}/analyze")
def analyze_media(project_id: str, media_id: str, scene_threshold: float = 0.3) -> dict:
    media_rows = [json.loads(r) for r in db.list_source_media(project_id)]
    media = next((m for m in media_rows if m["id"] == media_id), None)
    if not media:
        raise HTTPException(404, "media not found for project")

    cuts = scenes_mod.detect_scene_cuts(media["path"], threshold=scene_threshold)
    windows = scenes_mod.build_scene_windows(cuts, media["duration_sec"])

    project = Project.model_validate_json(db.get_project(project_id))
    timeline = build_rough_cut_from_scene_cuts(
        project_id=project_id,
        media_id=media_id,
        preset=project.preset,
        width=media["width"],
        height=media["height"],
        fps=media["fps"],
        total_duration_sec=media["duration_sec"],
        windows=windows,
    )
    db.upsert_timeline(timeline)
    project.status = ProjectStatus.ready
    db.upsert_project(project)
    return {"detected_cuts": cuts, "windows": windows, "timeline_id": timeline.id}


@app.get("/projects/{project_id}/timeline")
def get_timeline(project_id: str) -> dict:
    raw = db.get_timeline_for_project(project_id)
    if not raw:
        raise HTTPException(404, "no timeline for project yet")
    return json.loads(raw)


@app.put("/projects/{project_id}/timeline")
def put_timeline(project_id: str, timeline: TimelineDocument) -> dict:
    if timeline.project_id != project_id:
        raise HTTPException(400, "timeline.project_id mismatch")
    db.upsert_timeline(timeline)
    return {"ok": True}


# ---- render ----


class RenderRequest(BaseModel):
    media_id: str
    sfx_density: str = "balanced"
    target_lufs: float = -14.0


@app.post("/projects/{project_id}/render")
def render_project(project_id: str, req: RenderRequest) -> dict:
    timeline_raw = db.get_timeline_for_project(project_id)
    if not timeline_raw:
        raise HTTPException(400, "build a timeline before rendering")
    timeline = TimelineDocument.model_validate_json(timeline_raw)

    media_rows = [json.loads(r) for r in db.list_source_media(project_id)]
    media = next((m for m in media_rows if m["id"] == req.media_id), None)
    if not media:
        raise HTTPException(404, "media not found")

    work_dir = DATA_DIR / "renders" / project_id
    work_dir.mkdir(parents=True, exist_ok=True)

    for nb in timeline.narration:
        if nb.duration_sec <= 0:
            nb.duration_sec = tts.estimate_duration_sec(nb.text)
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
        cues.assign_assets(timeline.sound_cue_plan, asset_ids, density=req.sfx_density)
    sfx_items = [
        (asset_paths[c.audio_asset_id], c.output_start_ms, c.gain_db)
        for c in (timeline.sound_cue_plan.cues if timeline.sound_cue_plan else [])
        if c.audio_asset_id in asset_paths
    ]
    sfx_track = mix.place_sounds_on_track(sfx_items, timeline.total_duration_sec, work_dir / "sfx_bus.wav")
    vo_items = [
        (nb.audio_path, int(nb.output_start_sec * 1000), 0.0)
        for nb in timeline.narration if nb.audio_path
    ]
    voice_track = mix.place_sounds_on_track(vo_items, timeline.total_duration_sec, work_dir / "voice_bus.wav")
    game_track = mix.extract_game_audio(media["path"], timeline.total_duration_sec, work_dir / "game_bus.wav")
    music_track = mix.loop_music(music_asset.file_path, timeline.total_duration_sec, work_dir / "music_bus_raw.wav")
    ducked = mix.duck_against_voice(music_track, voice_track, work_dir / "music_bus_ducked.wav")
    final_raw = mix.mix_stems([voice_track, sfx_track, game_track, ducked], work_dir / "final_mix_raw.wav")
    final_audio = mix.normalize_to_target(final_raw, work_dir / "final_mix.wav", target_lufs=req.target_lufs)

    cutout_png = make_cutout_png(work_dir / "cutout.png")
    out_video = ffmpeg_render.render(
        media_path=media["path"],
        scenes=timeline.scenes,
        motions=timeline.motion,
        graphics=timeline.graphics,
        captions=captions,
        cutout_png=cutout_png,
        final_audio_path=final_audio,
        out_path=work_dir / "final.mp4",
        preset=timeline.preset,
        width=media["width"] if timeline.preset == AspectPreset.LONG_FORM_STORY else media["width"],
        height=media["height"],
        fps=media["fps"],
    )

    report = mix.loudness_report(final_audio)
    db.upsert_timeline(timeline)

    project = Project.model_validate_json(db.get_project(project_id))
    project.status = ProjectStatus.rendered
    db.upsert_project(project)

    return {"video_path": out_video, "audio_mix_path": final_audio, "loudness_report": report}


# ---- export ----


@app.get("/projects/{project_id}/export/otio")
def export_otio(project_id: str, media_id: str) -> dict:
    timeline = TimelineDocument.model_validate_json(db.get_timeline_for_project(project_id))
    media = next(json.loads(r) for r in db.list_source_media(project_id) if json.loads(r)["id"] == media_id)
    out = DATA_DIR / "exports" / project_id / "timeline.otio"
    path = otio_export.export_otio(timeline, media["path"], out)
    return {"path": path}


@app.get("/projects/{project_id}/export/fcpxml")
def export_fcpxml(project_id: str, media_id: str) -> dict:
    timeline = TimelineDocument.model_validate_json(db.get_timeline_for_project(project_id))
    media = next(json.loads(r) for r in db.list_source_media(project_id) if json.loads(r)["id"] == media_id)
    out = DATA_DIR / "exports" / project_id / "timeline.fcpxml"
    path = otio_export.export_fcpxml(timeline, media["path"], out)
    return {"path": path}


@app.get("/projects/{project_id}/export/timeline.json")
def export_timeline_json(project_id: str) -> dict:
    raw = db.get_timeline_for_project(project_id)
    if not raw:
        raise HTTPException(404, "no timeline")
    out = DATA_DIR / "exports" / project_id / "timeline.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(raw, encoding="utf-8")
    return {"path": str(out)}


@app.get("/projects/{project_id}/export/srt")
def export_srt(project_id: str, mode: str = "selective") -> dict:
    timeline = TimelineDocument.model_validate_json(db.get_timeline_for_project(project_id))
    out_dir = DATA_DIR / "exports" / project_id
    if mode == "full":
        path = srt_export.export_full_srt(timeline.narration, out_dir / "full.srt")
    else:
        captions = ffmpeg_render.select_kinetic_caption_words(timeline.narration)
        path = srt_export.export_selective_srt(captions, out_dir / "selective.srt")
    return {"path": path, "mode": mode}


# ---- skills ----


@app.get("/skills")
def list_skills(enabled_only: bool = False) -> list[dict]:
    return [json.loads(s) for s in db.list_skills(enabled_only)]


@app.post("/skills/import")
async def import_skill(file: UploadFile) -> dict:
    tmp_path = DATA_DIR / "tmp_skill_upload.md"
    tmp_path.write_bytes(await file.read())
    try:
        manifest = skills_loader.import_user_skill_md(tmp_path, SKILLS_LIBRARY_DIR)
    except ValueError as e:
        raise HTTPException(400, str(e))
    db.upsert_skill(manifest)
    return json.loads(manifest.model_dump_json())


@app.post("/skills/{skill_id}/approve")
def approve_skill(skill_id: str) -> dict:
    skills_loader.approve_skill(skill_id)
    return {"ok": True}


@app.get("/skills/{skill_id}/versions")
def skill_versions(skill_id: str) -> list[dict]:
    return [json.loads(v) for v in db.list_skill_versions(skill_id)]


# ---- memory / creative brief ----


@app.get("/memory")
def list_memory(kind: str | None = None) -> list[dict]:
    k = MemoryRecordKind(kind) if kind else None
    return [json.loads(r.model_dump_json()) for r in memory_store.recall(k)]


class RememberRequest(BaseModel):
    kind: MemoryRecordKind
    key: str
    value: dict


@app.post("/memory")
def remember(req: RememberRequest) -> dict:
    record = memory_store.remember(req.kind, req.key, req.value)
    return json.loads(record.model_dump_json())


class IntentRequest(BaseModel):
    text: str
    project_id: str | None = None


@app.post("/creative-brief")
def creative_brief(req: IntentRequest) -> dict:
    action = parse_intent(req.text)
    record = memory_store.record_feedback(req.text, action, project_id=req.project_id)
    return {"action": action, "feedback_id": record.id}


# ---- compute ----


@app.get("/compute/providers")
def compute_status() -> list[dict]:
    return compute_providers.list_providers()
