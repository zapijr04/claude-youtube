"""OTIO / FCPXML cutlist export for DaVinci Resolve (or any OTIO-aware NLE).

Builds a real opentimelineio.schema.Timeline from the TimelineDocument's
Scene list (source in/out, output position) with StoryBeat markers, then
writes both native `.otio` JSON and `.fcpxml` via the installed
`otio-fcpx-xml-adapter`. Both are round-trip-verified by reading them back
with OTIO's own adapters immediately after writing -- so "exported" here
means "a conforming file that OTIO itself can re-parse", not just "a file
was written". Whether DaVinci Resolve's GUI actually imports the FCPXML
has NOT been tested in this headless environment -- there is no Resolve
installation here -- and must not be claimed as verified.
"""
from __future__ import annotations

from pathlib import Path

import opentimelineio as otio

from app.schemas import StoryBeat, TimelineDocument


def build_otio_timeline(timeline: TimelineDocument, media_path: str) -> otio.schema.Timeline:
    otio_timeline = otio.schema.Timeline(name=f"noobzy-{timeline.project_id}")
    track = otio.schema.Track(name="V1 (NOOBZY rough cut)")
    otio_timeline.tracks.append(track)

    media_ref = otio.schema.ExternalReference(
        target_url=Path(media_path).resolve().as_uri(),
        available_range=otio.opentime.TimeRange(
            start_time=otio.opentime.RationalTime(0, timeline.fps),
            duration=otio.opentime.RationalTime(timeline.total_duration_sec * timeline.fps, timeline.fps),
        ),
    )

    for scene in timeline.scenes:
        in_frame = round(scene.source_in_sec * timeline.fps)
        out_frame = round(scene.source_out_sec * timeline.fps)
        clip = otio.schema.Clip(
            name=scene.reason or scene.id,
            media_reference=media_ref,
            source_range=otio.opentime.TimeRange(
                start_time=otio.opentime.RationalTime(in_frame, timeline.fps),
                duration=otio.opentime.RationalTime(out_frame - in_frame, timeline.fps),
            ),
        )
        track.append(clip)

    _add_beat_markers(otio_timeline, track, timeline.beats, timeline.fps)
    return otio_timeline


def _add_beat_markers(otio_timeline, track, beats: list[StoryBeat], fps: float) -> None:
    for beat in beats:
        marker = otio.schema.Marker(
            name=f"{beat.kind.value}: {beat.summary}"[:80],
            marked_range=otio.opentime.TimeRange(
                start_time=otio.opentime.RationalTime(beat.output_start_sec * fps, fps),
                duration=otio.opentime.RationalTime(1, fps),
            ),
            color=otio.schema.MarkerColor.CYAN,
        )
        track.markers.append(marker)


def export_otio(timeline: TimelineDocument, media_path: str, out_path: str | Path) -> str:
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    otio_timeline = build_otio_timeline(timeline, media_path)
    otio.adapters.write_to_file(otio_timeline, str(out_path))
    # round-trip verification -- prove the file we just wrote actually parses
    reread = otio.adapters.read_from_file(str(out_path))
    assert len(reread.tracks[0]) == len(timeline.scenes), "OTIO round-trip clip count mismatch"
    return str(out_path)


def export_fcpxml(timeline: TimelineDocument, media_path: str, out_path: str | Path) -> str:
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    otio_timeline = build_otio_timeline(timeline, media_path)
    otio.adapters.write_to_file(otio_timeline, str(out_path), adapter_name="fcpx_xml")
    reread = otio.adapters.read_from_file(str(out_path), adapter_name="fcpx_xml")
    assert len(reread.tracks[0]) == len(timeline.scenes), "FCPXML round-trip clip count mismatch"
    return str(out_path)
