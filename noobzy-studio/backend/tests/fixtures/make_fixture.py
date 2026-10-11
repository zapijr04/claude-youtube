"""Generates deterministic, clearly-synthetic gameplay-like test fixtures.

These are NOT real Roblox footage. Every "event" (egg open, chase, fail,
counter tick, reveal) is a label baked into a colored test card by FFmpeg,
with an explicit sidecar JSON of SIMULATED annotations at known timestamps.
Nothing here claims to have been recognized by AI from real footage -- the
ground truth is authored by this script, which is the point: it lets the
pipeline's scene-cut detector, timeline builder, and renderer be verified
against known-correct answers.

Produces:
  fixture_long.mp4   (~75s, 16:9, 1920x1080) -- Roblox "Steal an Egg" robbery
                      challenge: hook, goal/0-6 counter, chase, near-miss,
                      fail, setback, climax/6-6 counter, payoff.
  fixture_short.mp4  (~30s, 16:9 source later reframed to 9:16) -- THREE
                      Special Egg openings (Shorts-only premise, kept
                      structurally separate from the long-form fixture).

Each fixture has a `<name>.events.json` sidecar: list of
{at_sec, label, kind} ground-truth simulated events.
"""
from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Segment:
    label: str
    kind: str
    duration: float
    color: str
    tone_hz: float | None  # None = silence (tests silence/gap detection)
    moving_box: bool = False


LONG_SEGMENTS: list[Segment] = [
    Segment("HOOK: I TRIED TO ROB EVERY PLAYER", "hook", 8, "0x0E7CFF", 440),
    Segment("GOAL: STEAL 6 EGGS - 0/6", "goal", 10, "0x113355", 392),
    Segment("CHASE: GUARD INCOMING", "chase", 12, "0xCC2222", 523, moving_box=True),
    Segment("NEAR MISS", "near_miss", 6, "0xCC8800", 660),
    Segment("CAUGHT - FAILED ATTEMPT", "fail", 8, "0x222222", None),
    Segment("STRATEGY CHANGE", "strategy", 10, "0x224422", 349),
    Segment("CLIMAX: FINAL EGG - 6/6", "climax", 11, "0xFFD700", 784, moving_box=True),
    Segment("PAYOFF: ALL 6 STOLEN", "payoff", 10, "0x00CC66", 988),
]

SHORT_SEGMENTS: list[Segment] = [
    Segment("EGG 1: ANTICIPATION", "egg_anticipation_1", 3, "0x111111", None),
    Segment("EGG 1 REVEAL: COMMON", "egg_reveal_1", 4, "0x4477AA", 440),
    Segment("EGG 2: ANTICIPATION", "egg_anticipation_2", 3, "0x111111", None),
    Segment("EGG 2 REVEAL: RARE", "egg_reveal_2", 4, "0xAA66FF", 659),
    Segment("EGG 3: ANTICIPATION", "egg_anticipation_3", 3, "0x111111", None),
    Segment("EGG 3 REVEAL: LEGENDARY!!", "egg_reveal_3", 5, "0xFFD700", 1046, moving_box=True),
    Segment("RESULT COMPARISON", "comparison", 5, "0x222222", 392),
]


def _escape(text: str) -> str:
    return text.replace(":", r"\:").replace("'", r"\'")


def _segment_filter(seg: Segment, w: int, h: int, fps: int, idx: int) -> tuple[str, str]:
    """Return (video_filter_chain, audio_filter_chain) producing labeled streams."""
    vlabel = f"v{idx}"
    alabel = f"a{idx}"
    box = ""
    if seg.moving_box:
        # A synthetic colored square sliding left->right: stand-in for a
        # trackable "character/egg" object, clearly a placeholder shape.
        box = (
            f",drawbox=x='(iw-120)*t/{seg.duration}':y=ih/2-60:w=120:h=120:"
            f"color=white@0.9:t=fill"
        )
    vf = (
        f"color=c={seg.color}:s={w}x{h}:d={seg.duration}:r={fps}[c{idx}];"
        f"[c{idx}]drawtext=text='{_escape(seg.label)}':fontcolor=white:fontsize=54:"
        f"x=(w-text_w)/2:y=(h-text_h)/2:box=1:boxcolor=black@0.4:boxborderw=20"
        f"{box},setsar=1[{vlabel}]"
    )
    if seg.tone_hz:
        af = f"sine=frequency={seg.tone_hz}:duration={seg.duration}:sample_rate=48000[{alabel}]"
    else:
        af = f"anullsrc=channel_layout=stereo:sample_rate=48000:duration={seg.duration}[{alabel}]"
    return vf, af


def build_fixture(
    segments: list[Segment], out_path: Path, w: int = 1920, h: int = 1080, fps: int = 30
) -> list[dict]:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    filters = []
    vlabels = []
    alabels = []
    for i, seg in enumerate(segments):
        vf, af = _segment_filter(seg, w, h, fps, i)
        filters.append(vf)
        filters.append(af)
        vlabels.append(f"[v{i}]")
        alabels.append(f"[a{i}]")
    concat_v = "".join(vlabels) + f"concat=n={len(segments)}:v=1:a=0[outv]"
    concat_a = "".join(alabels) + f"concat=n={len(segments)}:v=0:a=1[outa]"
    filter_complex = ";".join(filters) + ";" + concat_v + ";" + concat_a

    cmd = [
        "ffmpeg", "-y",
        "-filter_complex", filter_complex,
        "-map", "[outv]", "-map", "[outa]",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "veryfast",
        "-c:a", "aac", "-b:a", "128k",
        str(out_path),
    ]
    subprocess.run(cmd, check=True, capture_output=True)

    events = []
    t = 0.0
    for seg in segments:
        events.append({"at_sec": round(t, 2), "label": seg.label, "kind": seg.kind, "simulated": True})
        t += seg.duration
    events.append({"at_sec": round(t, 2), "label": "END", "kind": "end", "simulated": True})

    sidecar = out_path.with_suffix("")
    sidecar = sidecar.parent / f"{sidecar.name}.events.json"
    sidecar.write_text(json.dumps({"total_duration_sec": t, "events": events}, indent=2))
    return events


def build_long_fixture(out_dir: Path) -> Path:
    out_path = out_dir / "fixture_long.mp4"
    build_fixture(LONG_SEGMENTS, out_path)
    return out_path


def build_short_fixture(out_dir: Path) -> Path:
    out_path = out_dir / "fixture_short.mp4"
    build_fixture(SHORT_SEGMENTS, out_path)
    return out_path


if __name__ == "__main__":
    out_dir = Path(__file__).resolve().parent / "generated"
    long_path = build_long_fixture(out_dir)
    short_path = build_short_fixture(out_dir)
    print("Built:", long_path)
    print("Built:", short_path)
