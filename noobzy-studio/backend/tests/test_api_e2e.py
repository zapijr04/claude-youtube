"""Full HTTP lifecycle test against the real FastAPI app (in-process, via
Starlette's TestClient -- exercises the actual route handlers, not mocks)."""
import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(scope="module")
def client():
    # Must be used as a context manager so FastAPI's startup event (DB
    # migrations + skill seeding) actually fires -- a bare TestClient(app)
    # does not run lifespan events in this Starlette version, which was
    # caught by test_skills_endpoints_over_http failing with 0 skills.
    with TestClient(app) as c:
        yield c


def test_full_project_lifecycle_over_http(client, long_fixture):
    r = client.post("/projects", json={"name": "E2E Test", "preset": "LONG_FORM_STORY", "target_duration_sec": 75})
    assert r.status_code == 200
    project = r.json()
    pid = project["id"]

    with open(long_fixture["path"], "rb") as f:
        r = client.post(f"/projects/{pid}/media", files={"file": ("fixture_long.mp4", f, "video/mp4")})
    assert r.status_code == 200
    media = r.json()
    mid = media["id"]
    assert media["codec"] == "h264"
    assert len(media["thumbnails"]) == 5

    r = client.post(f"/projects/{pid}/analyze", params={"media_id": mid})
    assert r.status_code == 200
    analysis = r.json()
    assert len(analysis["windows"]) >= 5

    r = client.get(f"/projects/{pid}/timeline")
    assert r.status_code == 200
    assert len(r.json()["scenes"]) == len(analysis["windows"])

    # Point 6: preview is cheap/cached and must never touch the export dir.
    r = client.post(f"/projects/{pid}/preview", json={"media_id": mid})
    assert r.status_code == 200
    preview = r.json()
    assert preview["loudness_report"]["clipping_detected"] is False
    assert "voice_coverage_report" in preview

    from app.media.ffprobe_util import probe
    info = probe(preview["video_path"])
    assert info["width"] == 1920 and info["has_audio"]

    # The ONE explicit final-export action actually writes the output MP4.
    r = client.post(f"/projects/{pid}/export/final-video", json={"media_id": mid})
    assert r.status_code == 200
    final = r.json()
    final_info = probe(final["video_path"])
    assert final_info["has_audio"] and final_info["duration_sec"] > 0
    assert len(final["new_mp4_files_in_output_dir"]) == 1

    r = client.get(f"/projects/{pid}/export/final-video/history")
    assert r.status_code == 200
    assert r.json()[-1]["status"] == "finalized"

    r = client.get(f"/projects/{pid}/export/otio", params={"media_id": mid})
    assert r.status_code == 200
    r = client.get(f"/projects/{pid}/export/srt", params={"mode": "selective"})
    assert r.status_code == 200


def test_narration_regen_speed_ramp_and_gap_report_over_http(client, long_fixture):
    r = client.post("/projects", json={"name": "V2 Features", "preset": "LONG_FORM_STORY", "target_duration_sec": 75})
    pid = r.json()["id"]
    with open(long_fixture["path"], "rb") as f:
        r = client.post(f"/projects/{pid}/media", files={"file": ("fixture_long.mp4", f, "video/mp4")})
    mid = r.json()["id"]
    r = client.post(f"/projects/{pid}/analyze", params={"media_id": mid})
    assert r.status_code == 200

    r = client.get(f"/projects/{pid}/voice-coverage-report")
    assert r.status_code == 200
    report = r.json()
    assert "voice_coverage_ratio" in report

    timeline = client.get(f"/projects/{pid}/timeline").json()
    scene_id = timeline["scenes"][0]["id"]
    r = client.post(f"/projects/{pid}/scenes/{scene_id}/speed-ramp", json={"rate": 2.0})
    assert r.status_code == 200
    assert r.json()["new_total_duration_sec"] < timeline["total_duration_sec"]

    timeline2 = client.get(f"/projects/{pid}/timeline").json()
    if timeline2["narration"]:
        block_id = timeline2["narration"][0]["id"]
        r = client.post(f"/projects/{pid}/narration/{block_id}/regenerate")
        assert r.status_code == 200
        assert r.json()["ok"] is True

    r = client.get(f"/projects/{pid}/timeline/versions")
    assert r.status_code == 200
    assert len(r.json()) >= 3  # analyze + speed-ramp + (maybe) narration regen


def test_analyze_with_narration_script_and_auto_style_over_http(client, long_fixture):
    r = client.post("/projects", json={"name": "Auto Upload", "preset": "LONG_FORM_STORY", "target_duration_sec": 75})
    pid = r.json()["id"]
    with open(long_fixture["path"], "rb") as f:
        r = client.post(f"/projects/{pid}/media", files={"file": ("fixture_long.mp4", f, "video/mp4")})
    mid = r.json()["id"]

    script = (
        "I tried to rob every player on this server. First I scoped out a target. "
        "He spotted me almost immediately and the chase was on. That was way too close. "
        "I had to back off and rethink my approach. This is the moment it all came together. "
        "In the end I walked away with everything."
    )
    r = client.post(
        f"/projects/{pid}/analyze",
        params={"media_id": mid},
        json={"narration_script": script, "auto_style": True},
    )
    assert r.status_code == 200

    timeline = client.get(f"/projects/{pid}/timeline").json()
    real_text = [nb["text"] for nb in timeline["narration"] if not nb["text"].startswith("[Add narration")]
    assert real_text, "at least one scene should carry real user-supplied text"
    assert timeline["motion"], "auto_style should add generic motion"
    assert timeline["sound_cue_plan"]["cues"], "auto_style should add transition SFX at real cut boundaries"


def test_skills_endpoints_over_http(client):
    r = client.get("/skills")
    assert r.status_code == 200
    skills = r.json()
    assert len(skills) >= 24
    ids = {s["id"] for s in skills}
    assert "noobzy-hook" in ids and "noobzy-sfx-auto" in ids


def test_creative_brief_endpoint_over_http(client):
    r = client.post("/creative-brief", json={"text": "give me more suspense before the reveal"})
    assert r.status_code == 200
    assert r.json()["action"]["action"] == "increase_anticipation"


def test_compute_providers_endpoint_over_http(client):
    r = client.get("/compute/providers")
    assert r.status_code == 200
    providers = {p["provider"] for p in r.json()}
    assert providers == {"local_cpu", "local_gpu", "comfyui_local", "runpod_gpu"}
