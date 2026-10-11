"""Skill loader/validator/importer.

A skill is a SKILL.md file with a small `---`-delimited front-matter block
(id/title/description/triggers/capabilities/dependencies/allowed_parameters/
examples) plus a markdown recipe body, next to a manifest.json mirror used
for fast DB-backed querying. Skills are declarative data (triggers, allowed
parameters, capability names consumed by the builder/render/audio modules)
-- never arbitrary executable code. Importing a user-authored skill parses
only this front matter; nothing is `eval`'d or executed from it.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from app import db
from app.schemas import SkillManifest

FRONT_MATTER_RE = re.compile(r"^---\n(.*?)\n---\n(.*)$", re.S)


def _render_skill_md(skill: dict) -> str:
    front = {
        "id": skill["id"],
        "version": skill.get("version", "1.0.0"),
        "title": skill["title"],
        "description": skill["description"],
        "triggers": skill.get("triggers", []),
        "capabilities": skill.get("capabilities", []),
        "dependencies": skill.get("dependencies", []),
        "allowed_parameters": skill.get("allowed_parameters", {}),
        "examples": skill.get("examples", []),
        "provenance": skill.get("provenance", "built_in"),
    }
    body = (
        f"# {skill['title']}\n\n"
        f"{skill['description']}\n\n"
        "## Triggers\n" + "\n".join(f"- {t}" for t in skill.get("triggers", [])) + "\n\n"
        "## Capabilities\n" + "\n".join(f"- {c}" for c in skill.get("capabilities", [])) + "\n\n"
        "## Examples\n" + "\n".join(f"- {e}" for e in skill.get("examples", [])) + "\n"
    )
    return "---\n" + json.dumps(front, indent=2) + "\n---\n\n" + body


def seed_builtin_skills(skills_library_dir: str | Path, skills: list[dict]) -> list[Path]:
    skills_library_dir = Path(skills_library_dir)
    written = []
    for skill in skills:
        skill_dir = skills_library_dir / skill["id"]
        skill_dir.mkdir(parents=True, exist_ok=True)
        md_path = skill_dir / "SKILL.md"
        manifest_path = skill_dir / "manifest.json"
        md_path.write_text(_render_skill_md(skill), encoding="utf-8")
        manifest = SkillManifest(
            id=skill["id"],
            title=skill["title"],
            description=skill["description"],
            triggers=skill.get("triggers", []),
            capabilities=skill.get("capabilities", []),
            dependencies=skill.get("dependencies", []),
            allowed_parameters=skill.get("allowed_parameters", {}),
            examples=skill.get("examples", []),
            provenance="built_in",
            skill_md_path=str(md_path),
        )
        manifest_path.write_text(manifest.model_dump_json(indent=2), encoding="utf-8")
        written.append(md_path)
    return written


def parse_skill_md(path: str | Path) -> SkillManifest:
    """Parse a SKILL.md's front matter into a validated SkillManifest.
    Raises ValueError for anything malformed -- never silently accepted."""
    path = Path(path)
    text = path.read_text(encoding="utf-8")
    m = FRONT_MATTER_RE.match(text)
    if not m:
        raise ValueError(f"{path}: missing '---' front-matter block")
    front = json.loads(m.group(1))
    required = {"id", "title", "description"}
    missing = required - front.keys()
    if missing:
        raise ValueError(f"{path}: front matter missing required fields {missing}")
    return SkillManifest(
        id=front["id"],
        version=front.get("version", "1.0.0"),
        title=front["title"],
        description=front["description"],
        triggers=front.get("triggers", []),
        capabilities=front.get("capabilities", []),
        dependencies=front.get("dependencies", []),
        allowed_parameters=front.get("allowed_parameters", {}),
        examples=front.get("examples", []),
        provenance=front.get("provenance", "user_imported"),
        skill_md_path=str(path),
    )


def load_all_from_dir(skills_library_dir: str | Path) -> list[SkillManifest]:
    skills_library_dir = Path(skills_library_dir)
    manifests = []
    for md_path in sorted(skills_library_dir.glob("*/SKILL.md")):
        manifests.append(parse_skill_md(md_path))
    return manifests


def persist_all(manifests: list[SkillManifest]) -> None:
    db.init_db()
    for m in manifests:
        db.upsert_skill(m)


def import_user_skill_md(markdown_path: str | Path, dest_library_dir: str | Path) -> SkillManifest:
    """Validate a user-supplied SKILL.md and stage it into the library dir
    under provenance='user_imported', pending the UI's approve step (the
    backend here only validates+stages; the API layer gates activation)."""
    manifest = parse_skill_md(markdown_path)  # raises if malformed
    dest_dir = Path(dest_library_dir) / manifest.id
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_md = dest_dir / "SKILL.md"
    dest_md.write_text(Path(markdown_path).read_text(encoding="utf-8"), encoding="utf-8")
    manifest.skill_md_path = str(dest_md)
    manifest.enabled = False  # requires explicit approval before activation
    (dest_dir / "manifest.json").write_text(manifest.model_dump_json(indent=2), encoding="utf-8")
    return manifest


def approve_skill(skill_id: str) -> None:
    db.set_skill_enabled(skill_id, True)
