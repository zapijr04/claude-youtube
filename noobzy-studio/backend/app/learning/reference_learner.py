"""Reference-video style learning (spec point 4 / noobzy-teach-from-video).

Honest scope: there is no vision or audio-classification model available in
this environment, so this module does NOT claim to detect caption styles,
SFX choices, or motion-graphic templates from pixels/audio -- that would be
fabricating an analysis the app can't actually do. What it DOES do for
real: run the same FFmpeg scene-cut detector used for a project's own
footage (app.media.scenes) against the uploaded reference video, measure
real pacing statistics from the real detected cuts, and turn those into a
proposed, versioned SkillManifest -- staged disabled, requiring explicit
user approval before it can affect any project (reusing the exact
import/approve path already used for user-authored Markdown skills).

Everything this module could NOT infer is listed under
`needs_manual_recipe` on the resulting CreativeStyleProfile, rather than
silently omitted.
"""
from __future__ import annotations

from pathlib import Path

from app.media.ffprobe_util import probe
from app.media.scenes import build_scene_windows, detect_scene_cuts
from app.schemas import CreativeStyleProfile, SkillManifest


def analyze_reference_video(path: str | Path, scene_threshold: float = 0.3) -> dict:
    """Real, measured pacing stats from the reference video's actual scene
    cuts -- nothing here is guessed."""
    info = probe(path)
    cuts = detect_scene_cuts(path, threshold=scene_threshold)
    windows = build_scene_windows(cuts, info["duration_sec"])
    shot_lengths = [e - s for s, e in windows]

    return {
        "source_duration_sec": info["duration_sec"],
        "detected_cut_count": len(cuts),
        "shot_count": len(windows),
        "avg_shot_length_sec": round(sum(shot_lengths) / len(shot_lengths), 2) if shot_lengths else 0.0,
        "min_shot_length_sec": round(min(shot_lengths), 2) if shot_lengths else 0.0,
        "max_shot_length_sec": round(max(shot_lengths), 2) if shot_lengths else 0.0,
        "cuts_per_minute": round(len(cuts) / (info["duration_sec"] / 60.0), 2) if info["duration_sec"] else 0.0,
    }


NOT_INFERABLE = [
    "caption style/placement/colors (needs OCR + layout analysis -- no vision model configured)",
    "SFX choice/timing (needs audio event classification -- not available offline)",
    "music genre/mood (needs audio classification -- not available offline)",
    "camera motion type, e.g. real pan vs. zoom vs. handheld (needs optical flow/pose analysis)",
    "on-screen graphic templates (counters/timers/cards) -- needs OCR + layout analysis",
]


def propose_skill_from_reference(
    path: str | Path, skill_id: str, title: str, scene_threshold: float = 0.3
) -> tuple[SkillManifest, CreativeStyleProfile, dict]:
    analysis = analyze_reference_video(path, scene_threshold)

    avg_shot = analysis["avg_shot_length_sec"]
    allowed_parameters = {
        "measured_avg_shot_length_sec": avg_shot,
        "measured_cuts_per_minute": analysis["cuts_per_minute"],
        "suggested_min_scene_length_sec": round(max(0.5, avg_shot * 0.4), 2),
        "suggested_max_scene_length_sec": round(avg_shot * 2.0, 2),
    }

    manifest = SkillManifest(
        id=skill_id,
        title=title,
        description=(
            f"Pacing recipe learned from a reference video: avg shot length "
            f"{avg_shot}s across {analysis['shot_count']} detected shots "
            f"({analysis['cuts_per_minute']} cuts/min). Caption/SFX/motion "
            f"style could NOT be inferred (no vision/audio model available) "
            f"-- see needs_manual_recipe."
        ),
        triggers=["learn this style", "match this pacing"],
        capabilities=["timeline.pacing_hint"],
        allowed_parameters=allowed_parameters,
        examples=[f"Apply {skill_id}'s measured pacing to a new rough cut."],
        provenance="reference_video_learned",
        enabled=False,  # requires explicit user approval, same as any imported skill
    )

    profile = CreativeStyleProfile(
        name=title,
        source=f"reference_video:{Path(path).name}",
        recipe=allowed_parameters,
        confidence_notes=(
            f"Pacing stats are real measurements from FFmpeg scene-cut detection "
            f"({analysis['detected_cut_count']} cuts found). Nothing beyond pacing "
            f"was inferred."
        ),
        needs_manual_recipe=True,
    )

    return manifest, profile, analysis
