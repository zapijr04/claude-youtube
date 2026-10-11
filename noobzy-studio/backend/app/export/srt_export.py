"""SRT export: selective (kinetic-caption keywords, default) or full
word-for-word subtitles -- a user-selected accessibility toggle, per spec."""
from __future__ import annotations

from pathlib import Path

from app.schemas import NarrationBlock


def _ts(seconds: float) -> str:
    seconds = max(0.0, seconds)
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int(round((seconds - int(seconds)) * 1000))
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def export_full_srt(narration: list[NarrationBlock], out_path: str | Path) -> str:
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    lines = []
    idx = 1
    for nb in narration:
        start = nb.output_start_sec
        end = nb.output_start_sec + nb.duration_sec
        lines.append(f"{idx}\n{_ts(start)} --> {_ts(end)}\n{nb.text}\n")
        idx += 1
    out_path.write_text("\n".join(lines), encoding="utf-8")
    return str(out_path)


def export_selective_srt(captions: list[dict], out_path: str | Path) -> str:
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    lines = []
    for idx, cap in enumerate(captions, start=1):
        lines.append(f"{idx}\n{_ts(cap['start'])} --> {_ts(cap['end'])}\n{cap['word'].upper()}\n")
    out_path.write_text("\n".join(lines), encoding="utf-8")
    return str(out_path)
