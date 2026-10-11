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

    r = client.post(f"/projects/{pid}/render", json={"media_id": mid})
    assert r.status_code == 200
    render = r.json()
    assert render["loudness_report"]["clipping_detected"] is False

    from app.media.ffprobe_util import probe
    info = probe(render["video_path"])
    assert info["width"] == 1920 and info["has_audio"]

    r = client.get(f"/projects/{pid}/export/otio", params={"media_id": mid})
    assert r.status_code == 200
    r = client.get(f"/projects/{pid}/export/srt", params={"mode": "selective"})
    assert r.status_code == 200


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
