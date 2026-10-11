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


def place_cues_on_track(
    cues: list,
    asset_paths: dict[str, str],
    total_duration_s: float,
    out_path: str | Path,
    sr: int = 48000,
) -> str:
    """Like place_sounds_on_track, but for SoundCue objects -- actually
    applies each cue's pitch_semitones and speed, not just gain/placement.
    Pitch shift uses asetrate+aresample+atempo (classic independent
    pitch-shift trick: resample to bend pitch, then atempo back to the
    original duration so only the pitch changed); `speed` is then layered
    on top via a second atempo stage. Both were a schema field that
    existed but was silently ignored by the old place_sounds_on_track --
    this is the real fix."""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    usable = [c for c in cues if c.audio_asset_id in asset_paths]
    if not usable:
        return place_sounds_on_track([], total_duration_s, out_path, sr)

    cmd = ["ffmpeg", "-y"]
    for c in usable:
        cmd += ["-i", asset_paths[c.audio_asset_id]]

    parts = []
    labels = []
    for i, c in enumerate(usable):
        stage_filters = []
        if abs(c.pitch_semitones) > 1e-6:
            ratio = 2 ** (c.pitch_semitones / 12.0)
            shifted_rate = int(sr * ratio)
            stage_filters.append(f"asetrate={shifted_rate}")
            stage_filters.append(f"aresample={sr}")
            stage_filters.append(f"atempo={1.0 / ratio:.6f}")
        if abs(c.speed - 1.0) > 1e-6:
            # atempo is only valid in [0.5, 2.0]; cue speeds are expected
            # to stay within that range for a short SFX hit.
            speed = min(2.0, max(0.5, c.speed))
            stage_filters.append(f"atempo={speed:.6f}")
        if c.gain_db:
            stage_filters.append(f"volume={c.gain_db}dB")
        stage_filters.append(f"adelay={max(0, c.output_start_ms)}:all=1")
        stage_filters.append("apad")
        parts.append(f"[{i}:a]{','.join(stage_filters)}[s{i}]")
        labels.append(f"[s{i}]")

    mix = "".join(labels) + f"amix=inputs={len(usable)}:normalize=0:dropout_transition=0[mixraw];[mixraw]alimiter=limit=0.9[mixed]"
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


def voice_coverage_gap_report(
    voice_track_path: str | Path, total_duration_s: float, gap_threshold_s: float = 1.25,
    silence_db: float = -35.0,
) -> dict:
    """Real silence detection on the ACTUAL rendered voice bus (FFmpeg's
    `silencedetect` filter, not just summed planned NarrationBlock
    durations) -- per spec: "calculate actual voice-speech occupancy from
    generated audio, not only intended script duration." Returns every
    silent interval plus which ones exceed `gap_threshold_s` (the ones that
    read as an unintentional dead-air stretch rather than a deliberate
    beat), and an overall speech-coverage ratio."""
    cmd = [
        "ffmpeg", "-i", str(voice_track_path),
        "-af", f"silencedetect=noise={silence_db}dB:d=0.3",
        "-f", "null", "-",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    starts = [float(m) for m in re.findall(r"silence_start:\s*(-?\d+\.?\d*)", result.stderr)]
    ends = [float(m) for m in re.findall(r"silence_end:\s*(-?\d+\.?\d*)", result.stderr)]

    # silencedetect may not emit a trailing silence_end if the file ends
    # silent; close it off at total_duration_s so coverage math stays sane.
    if len(ends) < len(starts):
        ends.append(total_duration_s)

    gaps = [
        {"start_sec": round(s, 2), "end_sec": round(e, 2), "duration_sec": round(e - s, 2)}
        for s, e in zip(starts, ends)
    ]
    total_silence = sum(g["duration_sec"] for g in gaps)
    coverage_ratio = max(0.0, 1.0 - (total_silence / total_duration_s)) if total_duration_s > 0 else 0.0
    over_threshold = [g for g in gaps if g["duration_sec"] > gap_threshold_s]

    return {
        "total_duration_sec": round(total_duration_s, 2),
        "voice_coverage_ratio": round(coverage_ratio, 4),
        "all_silent_gaps": gaps,
        "gaps_over_threshold": over_threshold,
        "gap_threshold_sec": gap_threshold_s,
    }


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
