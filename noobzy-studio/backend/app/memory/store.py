"""Persistent memory engine (spec section 5).

Independent, searchable, versioned memory for channel profile, creator
preferences, editing rules, approved skills, reference style analyses,
scene notes, production feedback and imported analytics. Every write bumps
the record's version and keeps provenance; nothing here reaches the
network -- it is pure local SQLite, seeded only from what the user
explicitly provides (per the "no imported ChatGPT history" constraint).
"""
from __future__ import annotations

import json
from pathlib import Path

from app import db
from app.schemas import CreativeFeedbackRecord, MemoryRecord, MemoryRecordKind


def remember(kind: MemoryRecordKind, key: str, value: dict, provenance: str = "user") -> MemoryRecord:
    """Create or update (by kind+key) a memory record, incrementing version."""
    existing = [json.loads(r) for r in db.list_memory(kind.value) if json.loads(r)["key"] == key]
    version = (existing[0]["version"] + 1) if existing else 1
    record_id = existing[0]["id"] if existing else None
    record = MemoryRecord(kind=kind, key=key, value=value, version=version, provenance=provenance)
    if record_id:
        record.id = record_id
    db.upsert_memory(record)
    return record


def recall(kind: MemoryRecordKind | None = None) -> list[MemoryRecord]:
    rows = db.list_memory(kind.value if kind else None)
    return [MemoryRecord.model_validate_json(r) for r in rows]


def search(query: str) -> list[MemoryRecord]:
    return [MemoryRecord.model_validate_json(r) for r in db.search_memory(query)]


def record_feedback(intent_text: str, parsed_action: dict, project_id: str | None = None, accepted: bool | None = None) -> CreativeFeedbackRecord:
    record = CreativeFeedbackRecord(
        project_id=project_id, intent_text=intent_text, parsed_action=parsed_action, accepted=accepted
    )
    db.insert_feedback(record)
    return record


def list_feedback(project_id: str | None = None) -> list[CreativeFeedbackRecord]:
    return [CreativeFeedbackRecord.model_validate_json(r) for r in db.list_feedback(project_id)]


def export_memory(out_path: str | Path) -> str:
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    records = [json.loads(r) for r in db.list_memory()]
    out_path.write_text(json.dumps(records, indent=2), encoding="utf-8")
    return str(out_path)


def import_memory(in_path: str | Path) -> int:
    records = json.loads(Path(in_path).read_text(encoding="utf-8"))
    count = 0
    for r in records:
        record = MemoryRecord.model_validate(r)
        db.upsert_memory(record)
        count += 1
    return count
