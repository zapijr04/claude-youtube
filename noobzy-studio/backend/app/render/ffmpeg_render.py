"""The real FFmpeg render engine: turns a TimelineDocument into an MP4.

Every effect below is an actual FFmpeg filter-graph stage, verified against
this build's filter set (not every eval function is available -- `floor`
and `clip` are not registered in this FFmpeg build's expression evaluator,
so easing uses `min`/`max`/`between`/`sin` instead, confirmed by direct CLI
probing before being wired in here).

Pipeline, in order:
  1. Cut: trim+concat the kept Scene windows from the source.
  2. Motion: zoom (smooth crop-bump) / shake (sinusoidal crop offset),
     scoped to each MotionPreset's time window.
  3. Cutout overlay: a second (alpha PNG) input composited with `overlay`,
     moving across its time window -- real alpha blending, not baked-in.
  4. Text: kinetic captions (selected keywords) + counters/timers/cards
     from GraphicLayers, all via `drawtext`, each scoped with `enable`.
  5. Reframe: for SHORT_EGG_REVEAL, crop+scale to 1080x1920.
  6. Mux with the externally-mixed final audio track (app.audio.mix).
"""
from __future__ import annotations

import subprocess
from pathlib import Path

from app.schemas import AspectPreset, GraphicLayer, GraphicLayerKind, MotionPreset, MotionPresetKind, Scene


def _esc_text(text: str) -> str:
    # ffmpeg drawtext text is wrapped in single quotes; a literal apostrophe
    # can't be safely nested there with simple backslash-escaping, so it's
    # dropped rather than risk a broken filtergraph for on-screen text.
    return (
        text.replace("'", "")
        .replace("\\", r"\\\\")
        .replace(":", r"\:")
        .replace(",", r"\,")
    )


def _clamp01(expr: str) -> str:
    return f"min(max({expr}\\,0)\\,1)"


def _cut_and_concat(scenes: list[Scene]) -> tuple[str, str]:
    """Trim+concat each kept Scene. A scene with playback_rate != 1.0 (a
    speed ramp -- app.timeline.retime.apply_speed_ramp) gets its PTS
    divided by the rate: rate>1 plays the same source material in less
    output time (sped up), rate<1 stretches it out (slow motion). The
    timeline's own output_start/end for everything downstream is kept
    consistent with this by the retime module, not by the renderer.
    """
    parts = []
    labels = []
    for i, sc in enumerate(scenes):
        rate_expr = f"(PTS-STARTPTS)/{sc.playback_rate:.6f}" if abs(sc.playback_rate - 1.0) > 1e-6 else "PTS-STARTPTS"
        parts.append(
            f"[0:v]trim=start={sc.source_in_sec:.3f}:end={sc.source_out_sec:.3f},"
            f"setpts={rate_expr}[s{i}]"
        )
        labels.append(f"[s{i}]")
    concat = "".join(labels) + f"concat=n={len(scenes)}:v=1:a=0[cut]"
    return ";".join(parts) + ";" + concat, "cut"


def _apply_motion(label_in: str, motions: list[MotionPreset], w: int, h: int) -> tuple[str, str]:
    stages = []
    cur = label_in
    for i, m in enumerate(motions):
        out = f"mo{i}"
        start, end = m.output_start_sec, m.output_end_sec
        progress = _clamp01(f"(t-{start:.3f})/{max(end - start, 0.01):.3f}")
        window = f"between(t\\,{start:.3f}\\,{end:.3f})"
        if m.kind == MotionPresetKind.zoom:
            bump = f"sin(PI*{progress})*{window}"
            margin_w = f"(0.08*{w})*{bump}"
            margin_h = f"(0.08*{h})*{bump}"
            stages.append(
                f"[{cur}]crop=w='{w}-2*({margin_w})':h='{h}-2*({margin_h})':"
                f"x='({margin_w})':y='({margin_h})',scale={w}:{h}[{out}]"
            )
        elif m.kind == MotionPresetKind.shake:
            amp_x = f"6*sin(2*PI*9*t)*{window}"
            amp_y = f"4*cos(2*PI*11*t)*{window}"
            margin = 24
            stages.append(
                f"[{cur}]crop=w='{w}-{2*margin}':h='{h}-{2*margin}':"
                f"x='{margin}+({amp_x})':y='{margin}+({amp_y})',scale={w}:{h}[{out}]"
            )
        else:
            stages.append(f"[{cur}]null[{out}]")
        cur = out
    return ";".join(stages), cur


def _apply_cutout(
    label_in: str, cutout_png_input_idx: int, layers: list[GraphicLayer], w: int, h: int
) -> tuple[str, str]:
    cutouts = [l for l in layers if l.kind == GraphicLayerKind.cutout_overlay]
    if not cutouts:
        return "", label_in
    stages = []
    cur = label_in
    for i, layer in enumerate(cutouts):
        start, end = layer.output_start_sec, layer.output_end_sec
        dur = max(end - start, 0.01)
        progress = _clamp01(f"(t-{start:.3f})/{dur:.3f}")
        x_expr = f"(main_w-overlay_w)*{progress}"
        y_expr = f"main_h/2-overlay_h/2-40*sin(2*PI*2*t)"
        out = f"cut{i}"
        stages.append(
            f"[{cur}][{cutout_png_input_idx}:v]overlay=x='{x_expr}':y='{y_expr}':"
            f"enable='between(t\\,{start:.3f}\\,{end:.3f})'[{out}]"
        )
        cur = out
    return ";".join(stages), cur


def _apply_text(label_in: str, layers: list[GraphicLayer], captions: list[dict], w: int, h: int) -> tuple[str, str]:
    stages = []
    cur = label_in
    idx = 0

    for layer in layers:
        if layer.kind == GraphicLayerKind.cutout_overlay:
            continue
        start, end = layer.output_start_sec, layer.output_end_sec
        enable = f"between(t\\,{start:.3f}\\,{end:.3f})"
        if layer.kind == GraphicLayerKind.counter:
            text = _esc_text(f"{layer.params.get('label','')}: {layer.params.get('value','')}")
            box = (
                f"drawtext=text='{text}':fontcolor=white:fontsize={int(h*0.045)}:"
                f"x=w-tw-40:y=40:box=1:boxcolor=0x0E7CFF@0.85:boxborderw=14:enable='{enable}'"
            )
        elif layer.kind == GraphicLayerKind.timer:
            # A REAL live countdown (ffmpeg's %{eif:...} text-expansion,
            # re-evaluated every frame), not a static label -- counts down
            # from params['from_sec'] (default: the layer's own window
            # length) to 0 as t runs from start to end.
            from_sec = int(layer.params.get("from_sec", round(end - start)))
            label = _esc_text(layer.params.get("label", "TIME LEFT"))
            countdown_expr = f"%{{eif\\:{from_sec}-(t-{start:.3f})\\:d}}"
            box = (
                f"drawtext=text='{label}\\: {countdown_expr}s':fontcolor=0xFFD700:"
                f"fontsize={int(h*0.05)}:x=40:y=40:box=1:boxcolor=black@0.6:boxborderw=14:"
                f"enable='{enable}'"
            )
        elif layer.kind == GraphicLayerKind.arrow:
            # A tracked pointer that slides across its window toward
            # whatever it's meant to call out (an egg, an upgrade, a
            # cutout subject) -- real per-frame motion via drawtext's own
            # x expression, not a static icon.
            progress = _clamp01(f"(t-{start:.3f})/{max(end - start, 0.01):.3f}")
            x_expr = f"(w-tw)*{progress}"
            box = (
                f"drawtext=text='→':font='DejaVu Sans':fontcolor=0xFFD700:"
                f"fontsize={int(h*0.09)}:x='{x_expr}':y=h*0.45:"
                f"borderw=3:bordercolor=black:enable='{enable}'"
            )
        elif layer.kind == GraphicLayerKind.end_screen:
            text = _esc_text(layer.params.get("text", ""))
            box = (
                f"drawtext=text='{text}':fontcolor=0x0E7CFF:fontsize={int(h*0.07)}:"
                f"x=(w-tw)/2:y=h*0.62:box=1:boxcolor=black@0.6:boxborderw=24:enable='{enable}'"
            )
        elif layer.kind in (GraphicLayerKind.hero_card, GraphicLayerKind.comparison_card):
            text = _esc_text(layer.params.get("text", ""))
            box = (
                f"drawtext=text='{text}':fontcolor=0xFFD700:fontsize={int(h*0.065)}:"
                f"x=(w-tw)/2:y=h*0.72:box=1:boxcolor=black@0.55:boxborderw=20:enable='{enable}'"
            )
        else:
            continue
        out = f"txt{idx}"
        stages.append(f"[{cur}]{box}[{out}]")
        cur = out
        idx += 1

    for cap in captions:
        text = _esc_text(cap["word"].upper())
        enable = f"between(t\\,{cap['start']:.3f}\\,{cap['end']:.3f})"
        box = (
            f"drawtext=text='{text}':fontcolor={cap.get('color','0x1FD1FF')}:"
            f"fontsize={int(h*0.06)}:x=(w-tw)/2:y=h*0.80:"
            f"borderw=4:bordercolor=black:enable='{enable}'"
        )
        out = f"cap{idx}"
        stages.append(f"[{cur}]{box}[{out}]")
        cur = out
        idx += 1

    if not stages:
        return "", cur
    return ";".join(stages), cur


def _reframe_vertical(label_in: str, src_w: int, src_h: int) -> tuple[str, str]:
    crop_w = int(src_h * 9 / 16)
    x = (src_w - crop_w) // 2
    stage = f"[{label_in}]crop=w={crop_w}:h={src_h}:x={x}:y=0,scale=1080:1920[vert]"
    return stage, "vert"


def select_kinetic_caption_words(narration, max_words: int = 14) -> list[dict]:
    """Pick emphasis words from narration alignment -- selective, not full
    word-for-word subtitles, per spec 8B.5 / noobzy-selective-captions."""
    stop = {"a", "an", "the", "is", "to", "of", "in", "that", "this", "it", "and", "i"}
    picks = []
    for nb in narration:
        for align in nb.alignment:
            w = align.word.strip(".,!?-").lower()
            if len(w) >= 5 and w not in stop:
                picks.append(
                    {
                        "word": align.word.strip(".,!?-"),
                        "start": nb.output_start_sec + align.start_ms / 1000.0,
                        "end": nb.output_start_sec + align.end_ms / 1000.0,
                        "color": "0xFFD700" if "!" in align.word or align.word.isupper() else "0x1FD1FF",
                    }
                )
    return picks[:max_words]


def render(
    media_path: str | Path,
    scenes: list[Scene],
    motions: list[MotionPreset],
    graphics: list[GraphicLayer],
    captions: list[dict],
    cutout_png: str | Path,
    final_audio_path: str | Path,
    out_path: str | Path,
    preset: AspectPreset,
    width: int = 1920,
    height: int = 1080,
    fps: float = 30.0,
    fast: bool = False,
) -> str:
    """fast=True is the preview-quality encode (app.pipeline.render_preview):
    same real filter graph and audio, just a much quicker x264 preset/CRF
    so repeated edits get a usable preview without the full-quality
    export's encode time. fast=False (the default) is the final-export
    quality used by app.pipeline.render_final_export."""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    cut_filter, cut_label = _cut_and_concat(scenes)
    motion_filter, motion_label = _apply_motion(cut_label, motions, width, height)
    cutout_filter, cutout_label = _apply_cutout(motion_label, 1, graphics, width, height)
    text_filter, text_label = _apply_text(cutout_label, graphics, captions, width, height)

    stages = [cut_filter]
    if motion_filter:
        stages.append(motion_filter)
    if cutout_filter:
        stages.append(cutout_filter)
    if text_filter:
        stages.append(text_filter)

    final_label = text_label
    if preset == AspectPreset.SHORT_EGG_REVEAL:
        reframe_filter, final_label = _reframe_vertical(final_label, width, height)
        stages.append(reframe_filter)

    filter_complex = ";".join(stages)

    x264_preset, crf, audio_bitrate = ("ultrafast", "30", "128k") if fast else ("medium", "20", "192k")
    cmd = [
        "ffmpeg", "-y",
        "-i", str(media_path),
        "-loop", "1", "-i", str(cutout_png),
        "-i", str(final_audio_path),
        "-filter_complex", filter_complex,
        "-map", f"[{final_label}]", "-map", "2:a",
        "-c:v", "libx264", "-preset", x264_preset, "-crf", crf, "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", audio_bitrate,
        "-shortest",
        str(out_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"render failed:\n{result.stderr[-4000:]}")
    return str(out_path)
