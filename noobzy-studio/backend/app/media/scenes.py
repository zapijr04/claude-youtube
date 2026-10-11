"""Real scene-cut detection using FFmpeg's `scene` scoring filter.

No opencv/pyscenedetect dependency required: ffmpeg's `select='gt(scene,T)'`
plus `showinfo` prints a `pts_time` for every frame whose scene-change score
exceeds the threshold. We parse stderr for those timestamps. This is a real
signal computed from actual pixel differences between frames, not a guess.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

_PTS_RE = re.compile(r"pts_time:(\d+\.?\d*)")


def detect_scene_cuts(src: str | Path, threshold: float = 0.3) -> list[float]:
    cmd = [
        "ffmpeg", "-i", str(src),
        "-filter:v", f"select='gt(scene,{threshold})',showinfo",
        "-f", "null", "-",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    cuts = [float(m.group(1)) for m in _PTS_RE.finditer(result.stderr)]
    return sorted(set(round(c, 2) for c in cuts))


def build_scene_windows(cuts: list[float], total_duration_sec: float) -> list[tuple[float, float]]:
    """Turn a sorted list of cut timestamps into contiguous (in, out) windows."""
    bounds = [0.0] + [c for c in cuts if 0.0 < c < total_duration_sec] + [total_duration_sec]
    bounds = sorted(set(bounds))
    return list(zip(bounds[:-1], bounds[1:]))
