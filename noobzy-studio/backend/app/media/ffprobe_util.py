"""Real FFprobe-backed media inspection. No guessed metadata."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any


class ProbeError(RuntimeError):
    pass


def probe(path: str | Path) -> dict[str, Any]:
    path = Path(path)
    if not path.exists():
        raise ProbeError(f"media file not found: {path}")
    cmd = [
        "ffprobe", "-v", "error", "-print_format", "json",
        "-show_format", "-show_streams", str(path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise ProbeError(f"ffprobe failed for {path}: {result.stderr.strip()}")
    data = json.loads(result.stdout)

    vstream = next((s for s in data["streams"] if s["codec_type"] == "video"), None)
    astream = next((s for s in data["streams"] if s["codec_type"] == "audio"), None)
    if vstream is None:
        raise ProbeError(f"no video stream found in {path}")

    num, den = (vstream.get("r_frame_rate") or "0/1").split("/")
    fps = float(num) / float(den) if float(den) else 0.0

    return {
        "codec": vstream.get("codec_name"),
        "width": int(vstream.get("width", 0)),
        "height": int(vstream.get("height", 0)),
        "fps": round(fps, 3),
        "duration_sec": float(data["format"].get("duration", 0.0)),
        "has_audio": astream is not None,
        "audio_codec": astream.get("codec_name") if astream else None,
        "size_bytes": int(data["format"].get("size", 0)),
    }
