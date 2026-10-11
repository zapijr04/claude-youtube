"""Generates small alpha-channel PNG assets used as overlay layers.

A real alpha-channel overlay (composited with ffmpeg's `overlay` filter) is
how section 8B's "transparent cutout" requirement is satisfied for the
acceptance test: a semi-transparent shape, clearly labeled as a synthetic
placeholder (no real segmented Roblox character available in this
environment), that moves across the frame and is correctly alpha-blended
on top of the base video -- as opposed to being baked into the source like
the fixture's own drawbox marker.
"""
from __future__ import annotations

import subprocess
from pathlib import Path


def make_cutout_png(out_path: str | Path, size: int = 160, color: str = "0x1FD1FF", alpha: float = 0.85) -> str:
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi",
        "-i", f"color=c={color}@{alpha}:s={size}x{size}",
        "-vf", "format=rgba,geq=lum='p(X,Y)':a='if(lt(hypot(X-W/2,Y-H/2),W/2),255,0)'",
        "-frames:v", "1",
        str(out_path),
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    return str(out_path)
