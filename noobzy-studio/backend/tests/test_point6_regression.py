"""Point 6 (non-negotiable) regression test.

Proves, across a REAL separate-process restart (not just a fresh object in
the same interpreter):
  1. 10+ edits can be applied to a project, each persisted as its own
     non-destructive timeline version.
  2. Zero MP4s exist anywhere under the project's final-export output
     directory while only editing/previewing is happening.
  3. After restart, the project and its latest edit are recoverable from
     SQLite, and a preview still works.
  4. Calling "Export Final Video" exactly once produces exactly one real,
     ffprobe-valid MP4 in the output directory -- and only then.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent

PHASE_A = r"""
import sys, json
sys.path.insert(0, {backend_dir!r})
from pathlib import Path
from fastapi.testclient import TestClient
from app.main import app

with TestClient(app) as client:
    r = client.post("/projects", json={{"name": "Point6 Test", "preset": "LONG_FORM_STORY", "target_duration_sec": 75}})
    assert r.status_code == 200, r.text
    project_id = r.json()["id"]

    with open({media_path!r}, "rb") as f:
        r = client.post(f"/projects/{{project_id}}/media", files={{"file": ("fixture_long.mp4", f, "video/mp4")}})
    assert r.status_code == 200, r.text
    media_id = r.json()["id"]

    r = client.post(f"/projects/{{project_id}}/analyze", params={{"media_id": media_id}})
    assert r.status_code == 200, r.text

    versions = []
    for i in range(10):
        r = client.get(f"/projects/{{project_id}}/timeline")
        assert r.status_code == 200
        tl = r.json()
        # A real, varied edit each iteration -- not a no-op.
        if tl["narration"]:
            tl["narration"][0]["text"] = f"Edited narration line number {{i}}."
        if tl.get("sound_cue_plan"):
            tl["sound_cue_plan"]["density"] = ["light", "balanced", "high-energy"][i % 3]
        tl["audio_tracks"][0]["gain_db"] = -1.0 * i
        tl["target_lufs"] = -14.0 - (i % 3)

        r = client.put(f"/projects/{{project_id}}/timeline", json=tl)
        assert r.status_code == 200, r.text
        versions.append(r.json()["version"])

    assert versions == sorted(versions), "versions must strictly increase"
    assert len(set(versions)) == 10, "each edit must be its own version"

    exports_dir = Path({data_dir!r}) / "exports"
    pre_mp4s = list(exports_dir.rglob("*.mp4")) if exports_dir.exists() else []
    assert pre_mp4s == [], f"found MP4(s) in output dir before any export: {{pre_mp4s}}"

    print(json.dumps({{
        "project_id": project_id,
        "media_id": media_id,
        "last_version": versions[-1],
        "last_narration_text": "Edited narration line number 9.",
    }}))
"""

PHASE_B = r"""
import sys, json
sys.path.insert(0, {backend_dir!r})
from pathlib import Path
from fastapi.testclient import TestClient
from app.main import app

project_id = {project_id!r}
media_id = {media_id!r}
expected_version = {expected_version!r}
expected_text = {expected_text!r}
data_dir = Path({data_dir!r})

with TestClient(app) as client:
    # 1. Recovered from SQLite after a genuine separate-process restart.
    r = client.get(f"/projects/{{project_id}}")
    assert r.status_code == 200, r.text

    r = client.get(f"/projects/{{project_id}}/timeline")
    assert r.status_code == 200
    tl = r.json()
    assert tl["narration"][0]["text"] == expected_text, tl["narration"][0]["text"]

    r = client.get(f"/projects/{{project_id}}/timeline/versions")
    versions = r.json()
    assert len(versions) >= expected_version, versions

    # 2. Preview works post-restart, and STILL touches nothing in exports/.
    r = client.post(f"/projects/{{project_id}}/preview", json={{"media_id": media_id}})
    assert r.status_code == 200, r.text
    preview_path = Path(r.json()["video_path"])
    assert preview_path.exists() and preview_path.stat().st_size > 0

    exports_dir = data_dir / "exports"
    pre_mp4s = list(exports_dir.rglob("*.mp4")) if exports_dir.exists() else []
    assert pre_mp4s == [], f"preview wrote into the export dir: {{pre_mp4s}}"

    # 3. The ONE explicit export action.
    r = client.post(f"/projects/{{project_id}}/export/final-video", json={{"media_id": media_id}})
    assert r.status_code == 200, r.text
    result = r.json()
    final_path = Path(result["video_path"])
    assert final_path.exists()

    all_mp4s = list(exports_dir.rglob("*.mp4"))
    assert len(all_mp4s) == 1, f"expected exactly one exported MP4, found {{all_mp4s}}"

    print(json.dumps({{"final_video_path": str(final_path), "mp4_count": len(all_mp4s)}}))
"""


def _run_phase(code: str, data_dir: Path) -> dict:
    env = {"NOOBZY_DATA_DIR": str(data_dir), "PATH": "/usr/bin:/bin"}
    result = subprocess.run(
        [sys.executable, "-c", code], cwd=BACKEND_DIR, env=env, capture_output=True, text=True,
    )
    assert result.returncode == 0, f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    return json.loads(result.stdout.strip().splitlines()[-1])


def test_ten_edits_restart_zero_pre_export_mp4s_one_final_export(tmp_path, long_fixture):
    data_dir = tmp_path / "data"

    phase_a_code = PHASE_A.format(
        backend_dir=str(BACKEND_DIR), media_path=str(long_fixture["path"]), data_dir=str(data_dir)
    )
    a = _run_phase(phase_a_code, data_dir)
    assert a["last_version"] >= 10

    phase_b_code = PHASE_B.format(
        backend_dir=str(BACKEND_DIR),
        project_id=a["project_id"],
        media_id=a["media_id"],
        expected_version=a["last_version"],
        expected_text=a["last_narration_text"],
        data_dir=str(data_dir),
    )
    b = _run_phase(phase_b_code, data_dir)
    assert b["mp4_count"] == 1

    from app.media.ffprobe_util import probe
    info = probe(b["final_video_path"])
    assert info["has_audio"]
    assert info["duration_sec"] > 0
