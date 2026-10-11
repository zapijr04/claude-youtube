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

from app import db, pipeline
from app.audio import mix
from app.audio import tts as tts_mod
from app.compute import providers as compute_providers
from app.creative_brief import parse_intent
from app.export import otio_export, srt_export
from app.media import ffprobe_util, proxy, scenes as scenes_mod
from app.memory import store as memory_store
from app.render import ffmpeg_render
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
from app.timeline.builder import build_rough_cut_from_scene_cuts, select_windows_for_target_duration
from app.timeline.retime import apply_speed_ramp, resync_after_narration_change

DATA_DIR = Path(db.DATA_DIR)
MEDIA_DIR = DATA_DIR / "media"
CACHE_DIR = DATA_DIR / "cache"  # ALL preview/proxy/intermediate artifacts live here
EXPORTS_DIR = DATA_DIR / "exports"  # default final-export output location
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
def analyze_media(
    project_id: str, media_id: str, scene_threshold: float = 0.3, apply_target_duration: bool = False
) -> dict:
    media_rows = [json.loads(r) for r in db.list_source_media(project_id)]
    media = next((m for m in media_rows if m["id"] == media_id), None)
    if not media:
        raise HTTPException(404, "media not found for project")

    cuts = scenes_mod.detect_scene_cuts(media["path"], threshold=scene_threshold)
    windows = scenes_mod.build_scene_windows(cuts, media["duration_sec"])

    project = Project.model_validate_json(db.get_project(project_id))

    selected_windows = windows
    if apply_target_duration:
        # The "~2h raw -> ~12m story" mode: see
        # app.timeline.builder.select_windows_for_target_duration for the
        # documented, honest heuristic (no AI engagement scoring exists
        # here -- this does not claim to find "the best" moments).
        selected_windows = select_windows_for_target_duration(windows, project.target_duration_sec)
    output_duration = sum(e - s for s, e in selected_windows)

    timeline = build_rough_cut_from_scene_cuts(
        project_id=project_id,
        media_id=media_id,
        preset=project.preset,
        width=media["width"],
        height=media["height"],
        fps=media["fps"],
        total_duration_sec=output_duration,
        windows=selected_windows,
    )
    db.upsert_timeline(timeline)
    project.status = ProjectStatus.ready
    db.upsert_project(project)
    return {
        "detected_cuts": cuts,
        "windows": windows,
        "selected_windows": selected_windows,
        "output_duration_sec": output_duration,
        "timeline_id": timeline.id,
    }


@app.get("/projects/{project_id}/timeline")
def get_timeline(project_id: str) -> dict:
    raw = db.get_timeline_for_project(project_id)
    if not raw:
        raise HTTPException(404, "no timeline for project yet")
    return json.loads(raw)


@app.put("/projects/{project_id}/timeline")
def put_timeline(project_id: str, timeline: TimelineDocument) -> dict:
    """The ONLY way edits are saved. Cheap: just persists the document and
    appends a version to timeline_versions (point 6) -- never touches a
    rendered MP4."""
    if timeline.project_id != project_id:
        raise HTTPException(400, "timeline.project_id mismatch")
    version = db.upsert_timeline(timeline)
    return {"ok": True, "version": version}


@app.get("/projects/{project_id}/timeline/versions")
def list_timeline_versions(project_id: str) -> list[dict]:
    return db.list_timeline_versions(project_id)


@app.post("/projects/{project_id}/timeline/rollback")
def rollback_timeline(project_id: str, version: int) -> dict:
    raw = db.get_timeline_version(project_id, version)
    if not raw:
        raise HTTPException(404, f"no timeline version {version} for this project")
    timeline = TimelineDocument.model_validate_json(raw)
    new_version = db.upsert_timeline(timeline)  # rollback is itself a new, non-destructive version
    return {"ok": True, "restored_from_version": version, "new_version": new_version}


# ---- preview (cheap, cached, never writes to a user export folder) ----


class PreviewRequest(BaseModel):
    media_id: str
    sfx_density: str = "balanced"


def _load_timeline_and_media(project_id: str, media_id: str) -> tuple[TimelineDocument, dict]:
    timeline_raw = db.get_timeline_for_project(project_id)
    if not timeline_raw:
        raise HTTPException(400, "build a timeline before rendering")
    timeline = TimelineDocument.model_validate_json(timeline_raw)

    media_rows = [json.loads(r) for r in db.list_source_media(project_id)]
    media = next((m for m in media_rows if m["id"] == media_id), None)
    if not media:
        raise HTTPException(404, "media not found")
    return timeline, media


@app.post("/projects/{project_id}/preview")
def preview_project(project_id: str, req: PreviewRequest) -> dict:
    """Fast, cache-reused preview render. Point 6: this NEVER writes into
    the project's final-export output directory -- only under the managed
    cache dir, keyed by a content hash of the current timeline so repeated
    calls with no real edit reuse the existing file instead of rebuilding."""
    timeline, media = _load_timeline_and_media(project_id, req.media_id)
    cache_dir = CACHE_DIR / project_id
    result = pipeline.render_preview(timeline, media, cache_dir, sfx_density=req.sfx_density)
    return result


# ---- export final video (the ONLY action that writes a finished MP4 to
# the user's chosen output location) ----


class ExportFinalVideoRequest(BaseModel):
    media_id: str
    sfx_density: str = "balanced"
    output_dir: str | None = None  # defaults to backend/data/exports/<project_id>/
    filename: str = "final.mp4"
    also_export_sidecars: bool = True  # SRT/OTIO/FCPXML/timeline.json alongside


@app.post("/projects/{project_id}/export/final-video")
def export_final_video(project_id: str, req: ExportFinalVideoRequest) -> dict:
    timeline, media = _load_timeline_and_media(project_id, req.media_id)
    cache_dir = CACHE_DIR / project_id
    output_dir = Path(req.output_dir) if req.output_dir else (EXPORTS_DIR / project_id)

    pre_existing = set(output_dir.glob("*.mp4")) if output_dir.exists() else set()

    try:
        result = pipeline.render_final_export(
            timeline, media, cache_dir, output_dir, req.filename, sfx_density=req.sfx_density
        )
    except RuntimeError as e:
        db.insert_final_export(
            {"id": db_new_export_id(), "project_id": project_id, "output_path": str(output_dir / req.filename), "status": "failed_qc", "error": str(e)}
        )
        raise HTTPException(500, str(e))

    if req.also_export_sidecars:
        result["sidecars"] = pipeline.export_sidecars(timeline, media["path"], output_dir, Path(req.filename).stem)

    db.insert_final_export(
        {
            "id": db_new_export_id(),
            "project_id": project_id,
            "output_path": result["video_path"],
            "status": "finalized",
        }
    )

    project = Project.model_validate_json(db.get_project(project_id))
    project.status = ProjectStatus.rendered
    db.upsert_project(project)

    after = set(output_dir.glob("*.mp4"))
    result["new_mp4_files_in_output_dir"] = sorted(str(p) for p in (after - pre_existing))
    return result


def db_new_export_id() -> str:
    from app.schemas import new_id
    return new_id("finalexp")


@app.get("/projects/{project_id}/export/final-video/history")
def final_video_history(project_id: str) -> list[dict]:
    return db.list_final_exports(project_id)


# ---- narration (ElevenLabs/local-fallback), regenerate one block at a time ----


@app.post("/projects/{project_id}/narration/{block_id}/regenerate")
def regenerate_narration_block(project_id: str, block_id: str) -> dict:
    """Regenerates exactly one NarrationBlock's audio (never a full
    render) and re-syncs every downstream timestamp so SFX/captions/duck
    stay aligned -- point 3's "regenerate one block at a time ... align
    SFX, music duck and captions after modifications"."""
    timeline_raw = db.get_timeline_for_project(project_id)
    if not timeline_raw:
        raise HTTPException(404, "no timeline for project")
    timeline = TimelineDocument.model_validate_json(timeline_raw)

    block = next((n for n in timeline.narration if n.id == block_id), None)
    if block is None:
        raise HTTPException(404, "narration block not found")

    cache_dir = CACHE_DIR / project_id / "vo"
    old_duration = block.duration_sec
    try:
        tts_mod.synthesize_elevenlabs(block, cache_dir)
    except tts_mod.ElevenLabsNotConfigured:
        tts_mod.synthesize_local_fallback(block, cache_dir)

    resync_after_narration_change(timeline, block_id)
    version = db.upsert_timeline(timeline)

    return {
        "ok": True,
        "version": version,
        "block": json.loads(block.model_dump_json()),
        "old_duration_sec": old_duration,
        "new_duration_sec": block.duration_sec,
    }


@app.get("/projects/{project_id}/voice-coverage-report")
def voice_coverage_report(project_id: str) -> dict:
    """Builds (or reuses, from cache) the voice bus for the CURRENT
    timeline and runs real silence detection on it -- actual rendered
    audio occupancy, not just summed planned durations."""
    timeline_raw = db.get_timeline_for_project(project_id)
    if not timeline_raw:
        raise HTTPException(404, "no timeline for project")
    timeline = TimelineDocument.model_validate_json(timeline_raw)

    cache_dir = CACHE_DIR / project_id / "vo"
    for nb in timeline.narration:
        if nb.duration_sec <= 0:
            nb.duration_sec = tts_mod.estimate_duration_sec(nb.text)
        if not nb.audio_path or not Path(nb.audio_path).exists():
            try:
                tts_mod.synthesize_elevenlabs(nb, cache_dir)
            except tts_mod.ElevenLabsNotConfigured:
                tts_mod.synthesize_local_fallback(nb, cache_dir)
    db.upsert_timeline(timeline)

    vo_items = [(nb.audio_path, int(nb.output_start_sec * 1000), 0.0) for nb in timeline.narration if nb.audio_path]
    voice_track = mix.place_sounds_on_track(
        vo_items, timeline.total_duration_sec, CACHE_DIR / project_id / "voice_report_bus.wav"
    )
    return mix.voice_coverage_gap_report(voice_track, timeline.total_duration_sec)


# ---- motion: speed ramp ----


class SpeedRampRequest(BaseModel):
    rate: float  # >1 = sped up, <1 = slow motion


@app.post("/projects/{project_id}/scenes/{scene_id}/speed-ramp")
def speed_ramp_scene(project_id: str, scene_id: str, req: SpeedRampRequest) -> dict:
    timeline_raw = db.get_timeline_for_project(project_id)
    if not timeline_raw:
        raise HTTPException(404, "no timeline for project")
    timeline = TimelineDocument.model_validate_json(timeline_raw)

    try:
        apply_speed_ramp(timeline, scene_id, req.rate)
    except ValueError as e:
        raise HTTPException(400, str(e))

    version = db.upsert_timeline(timeline)
    return {"ok": True, "version": version, "new_total_duration_sec": timeline.total_duration_sec}


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


@app.post("/skills/learn-from-reference")
async def learn_from_reference(file: UploadFile, skill_id: str, title: str) -> dict:
    """Uploads a reference/tutorial video, measures its real pacing via the
    same scene-cut detector used on a project's own footage, and stages a
    proposed skill -- disabled until POST /skills/{id}/approve. Nothing
    about captions/SFX/motion style is claimed; see needs_manual_recipe."""
    from app.learning.reference_learner import propose_skill_from_reference

    dest_dir = DATA_DIR / "reference_uploads"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_dir / file.filename
    with dest_path.open("wb") as f:
        shutil.copyfileobj(file.file, f)

    try:
        info = ffprobe_util.probe(dest_path)
    except ffprobe_util.ProbeError as e:
        raise HTTPException(400, str(e))

    manifest, profile, analysis = propose_skill_from_reference(dest_path, skill_id, title)

    dest_skill_dir = SKILLS_LIBRARY_DIR / manifest.id
    dest_skill_dir.mkdir(parents=True, exist_ok=True)
    (dest_skill_dir / "manifest.json").write_text(manifest.model_dump_json(indent=2))
    db.upsert_skill(manifest)

    memory_store.remember(
        MemoryRecordKind.reference_style_analysis, manifest.id, json.loads(profile.model_dump_json())
    )

    return {
        "manifest": json.loads(manifest.model_dump_json()),
        "style_profile": json.loads(profile.model_dump_json()),
        "analysis": analysis,
        "media_probe": info,
    }


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
