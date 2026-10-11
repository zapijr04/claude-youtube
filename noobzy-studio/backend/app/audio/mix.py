"""FFmpeg-based multi-bus audio mixing, ducking and loudness QC.

Buses: voice (A1), sfx (A2), game audio (A3), music (A4) -- each rendered as
its own stem WAV, then combined into a final mix with real sidechain
compression (ffmpeg's `sidechaincompress` filter) ducking the music bus
under the voice bus. Nothing here is a simulated "AI mix" label: every
operation is a documented FFmpeg/DSP filter actually executed and then
measured (RMS / loudnorm / volumedetect) to prove the effect happened.
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path


def _run(cmd: list[str]) -> subprocess.CompletedProcess:
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {' '.join(cmd)}\n{result.stderr[-2000:]}")
    return result


def place_sounds_on_track(
    items: list[tuple[str, int, float]], total_duration_s: float, out_path: str | Path, sr: int = 48000
) -> str:
    """items: list of (wav_path, start_ms, gain_db). Produces one mono WAV of
    length total_duration_s with every item placed at its start time."""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if not items:
        _run([
            "ffmpeg", "-y", "-f", "lavfi", "-i", f"anullsrc=r={sr}:cl=mono",
            "-t", f"{total_duration_s:.3f}", str(out_path),
        ])
        return str(out_path)

    cmd = ["ffmpeg", "-y"]
    for path, _, _ in items:
        cmd += ["-i", path]

    parts = []
    labels = []
    for i, (_, start_ms, gain_db) in enumerate(items):
        gain = f",volume={gain_db}dB" if gain_db else ""
        parts.append(f"[{i}:a]adelay={max(0, start_ms)}:all=1{gain},apad[s{i}]")
        labels.append(f"[s{i}]")
    mix = "".join(labels) + f"amix=inputs={len(items)}:normalize=0:dropout_transition=0[mixraw];[mixraw]alimiter=limit=0.9[mixed]"
    filter_complex = ";".join(parts) + ";" + mix

    cmd += [
        "-filter_complex", filter_complex,
        "-map", "[mixed]", "-t", f"{total_duration_s:.3f}",
        "-ar", str(sr), "-ac", "1",
        str(out_path),
    ]
    _run(cmd)
    return str(out_path)


def extract_game_audio(src_video: str | Path, total_duration_s: float, out_path: str | Path, gain_db: float = -6.0) -> str:
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    _run([
        "ffmpeg", "-y", "-i", str(src_video),
        "-t", f"{total_duration_s:.3f}", "-af", f"volume={gain_db}dB",
        "-ar", "48000", "-ac", "1", str(out_path),
    ])
    return str(out_path)


def loop_music(music_path: str | Path, total_duration_s: float, out_path: str | Path, gain_db: float = -14.0) -> str:
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    _run([
        "ffmpeg", "-y", "-stream_loop", "-1", "-i", str(music_path),
        "-t", f"{total_duration_s:.3f}", "-af", f"volume={gain_db}dB",
        "-ar", "48000", "-ac", "1", str(out_path),
    ])
    return str(out_path)


def duck_against_voice(
    music_path: str | Path, voice_path: str | Path, out_path: str | Path,
    threshold: float = 0.05, ratio: float = 8, attack_ms: float = 20, release_ms: float = 400,
) -> str:
    """Sidechain-compress the music bus using the voice bus as the trigger.

    This is real ffmpeg DSP (`sidechaincompress`), not a volume-keyframe
    approximation: the music genuinely drops in level whenever voice energy
    rises, and recovers smoothly on release.
    """
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    filter_complex = (
        f"[0:a][1:a]sidechaincompress=threshold={threshold}:ratio={ratio}:"
        f"attack={attack_ms}:release={release_ms}:makeup=1[ducked]"
    )
    _run([
        "ffmpeg", "-y", "-i", str(music_path), "-i", str(voice_path),
        "-filter_complex", filter_complex, "-map", "[ducked]",
        str(out_path),
    ])
    return str(out_path)


def mix_stems(stem_paths: list[str], out_path: str | Path) -> str:
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = ["ffmpeg", "-y"]
    for p in stem_paths:
        cmd += ["-i", p]
    labels = "".join(f"[{i}:a]" for i in range(len(stem_paths)))
    filter_complex = (
        f"{labels}amix=inputs={len(stem_paths)}:normalize=0:dropout_transition=0[mixraw];"
        f"[mixraw]alimiter=limit=0.95:attack=5:release=50[mixed]"
    )
    cmd += ["-filter_complex", filter_complex, "-map", "[mixed]", "-ar", "48000", "-ac", "2", str(out_path)]
    _run(cmd)
    return str(out_path)


def measure_rms_db(path: str | Path, start_s: float | None = None, end_s: float | None = None) -> float:
    """Mean RMS level in dBFS over [start_s, end_s) (or the whole file)."""
    cmd = ["ffmpeg"]
    if start_s is not None:
        cmd += ["-ss", f"{start_s:.3f}"]
    cmd += ["-i", str(path)]
    if end_s is not None:
        cmd += ["-t", f"{max(0.01, end_s - (start_s or 0)):.3f}"]
    cmd += ["-af", "astats=metadata=0", "-f", "null", "-"]
    result = subprocess.run(cmd, capture_output=True, text=True)
    matches = re.findall(r"RMS level dB:\s*(-?\d+\.?\d*|-inf)", result.stderr)
    if not matches:
        return float("-inf")
    vals = [float(m) for m in matches if m != "-inf"]
    return sum(vals) / len(vals) if vals else float("-inf")


def normalize_to_target(
    in_path: str | Path, out_path: str | Path, target_lufs: float = -14.0, target_tp: float = -1.0
) -> str:
    """One-pass loudnorm mastering toward a configurable LUFS/true-peak target
    (defaults mirror the YouTube-oriented starting preferences in spec A3;
    these are editable preferences, not an official YouTube requirement)."""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    _run([
        "ffmpeg", "-y", "-i", str(in_path),
        "-af", f"loudnorm=I={target_lufs}:TP={target_tp}:LRA=11",
        "-ar", "48000", str(out_path),
    ])
    return str(out_path)


def loudness_report(path: str | Path) -> dict:
    """Integrated LUFS / true-peak via FFmpeg's loudnorm measure pass, plus
    clipping detection via volumedetect."""
    cmd = [
        "ffmpeg", "-i", str(path),
        "-af", "loudnorm=print_format=json", "-f", "null", "-",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    m = re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", result.stderr, re.S)
    stats = json.loads(m.group(0)) if m else {}

    cmd2 = ["ffmpeg", "-i", str(path), "-af", "volumedetect", "-f", "null", "-"]
    result2 = subprocess.run(cmd2, capture_output=True, text=True)
    max_vol_match = re.search(r"max_volume:\s*(-?\d+\.?\d*) dB", result2.stderr)
    max_vol = float(max_vol_match.group(1)) if max_vol_match else None

    return {
        "integrated_lufs": float(stats.get("input_i", "nan")) if stats else None,
        "true_peak_dbtp": float(stats.get("input_tp", "nan")) if stats else None,
        "max_volume_db": max_vol,
        "clipping_detected": bool(max_vol is not None and max_vol >= -0.1),
    }
