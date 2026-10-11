"""Thumbnail, waveform, and low-res proxy generation via FFmpeg."""
from __future__ import annotations

import subprocess
from pathlib import Path


def generate_thumbnails(
    src: str | Path, out_dir: str | Path, count: int = 5, duration_sec: float | None = None
) -> list[str]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    if duration_sec is None:
        from .ffprobe_util import probe
        duration_sec = probe(src)["duration_sec"]

    paths = []
    for i in range(count):
        t = max(0.0, duration_sec * (i + 0.5) / count)
        out_path = out_dir / f"thumb_{i:02d}.jpg"
        cmd = [
            "ffmpeg", "-y", "-ss", f"{t:.2f}", "-i", str(src),
            "-frames:v", "1", "-vf", "scale=320:-1", str(out_path),
        ]
        subprocess.run(cmd, check=True, capture_output=True)
        paths.append(str(out_path))
    return paths


def generate_waveform(src: str | Path, out_path: str | Path, width: int = 1600, height: int = 200) -> str:
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg", "-y", "-i", str(src),
        "-filter_complex", f"showwavespic=s={width}x{height}:colors=0x1FD1FF",
        "-frames:v", "1", str(out_path),
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    return str(out_path)


def generate_proxy(src: str | Path, out_path: str | Path, max_height: int = 480) -> str:
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg", "-y", "-i", str(src),
        "-vf", f"scale=-2:{max_height}",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "28",
        "-c:a", "aac", "-b:a", "96k",
        str(out_path),
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    return str(out_path)
