import json
import subprocess
import sys
from pathlib import Path

import pytest

from app.skills import loader
from app.skills.seed_data import SKILLS

BACKEND_DIR = Path(__file__).resolve().parent.parent


def _run(code: str, data_dir: Path) -> str:
    env = {"NOOBZY_DATA_DIR": str(data_dir), "PATH": "/usr/bin:/bin"}
    result = subprocess.run(
        [sys.executable, "-c", code], cwd=BACKEND_DIR, env=env, capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout


def test_skills_survive_separate_process_restart(tmp_path):
    data_dir = tmp_path / "data"
    library_dir = tmp_path / "skills_library"

    _run(
        f"""
import sys; sys.path.insert(0, {str(BACKEND_DIR)!r})
from app.skills import loader
from app.skills.seed_data import SKILLS
loader.seed_builtin_skills({str(library_dir)!r}, SKILLS)
manifests = loader.load_all_from_dir({str(library_dir)!r})
loader.persist_all(manifests)
print(len(manifests))
""",
        data_dir,
    )

    out = _run(
        f"""
import sys; sys.path.insert(0, {str(BACKEND_DIR)!r})
from app import db
db.init_db()
print(len(db.list_skills()))
""",
        data_dir,
    )
    assert out.strip() == str(len(SKILLS))


def test_import_user_skill_md_validates_front_matter(tmp_path):
    bad = tmp_path / "bad.md"
    bad.write_text("# no front matter here")
    with pytest.raises(ValueError):
        loader.parse_skill_md(bad)

    good = tmp_path / "good.md"
    good.write_text(
        '---\n{"id": "noobzy-test-import", "title": "T", "description": "D"}\n---\n\nbody\n'
    )
    manifest = loader.parse_skill_md(good)
    assert manifest.id == "noobzy-test-import"
    assert manifest.provenance == "user_imported"


def test_import_user_skill_requires_approval_before_enabled(tmp_path):
    md = tmp_path / "new_skill.md"
    md.write_text(
        '---\n{"id": "noobzy-test-approval", "title": "T", "description": "D"}\n---\n\nbody\n'
    )
    dest_lib = tmp_path / "lib"
    manifest = loader.import_user_skill_md(md, dest_lib)
    assert manifest.enabled is False
    saved = json.loads((dest_lib / manifest.id / "manifest.json").read_text())
    assert saved["enabled"] is False


def test_skill_version_history_is_kept_on_update(tmp_path):
    data_dir = tmp_path / "data"
    out = _run(
        f"""
import sys; sys.path.insert(0, {str(BACKEND_DIR)!r})
from app import db
from app.schemas import SkillManifest
db.init_db()
m = SkillManifest(id="noobzy-versioned", title="T", description="D", version="1.0.0")
db.upsert_skill(m)
m.version = "1.1.0"
m.description = "updated"
db.upsert_skill(m)
versions = db.list_skill_versions("noobzy-versioned")
print(len(versions))
""",
        data_dir,
    )
    assert out.strip() == "2"
