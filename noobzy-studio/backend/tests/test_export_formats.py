import json
from pathlib import Path

import opentimelineio as otio

from app.export import otio_export, srt_export
from app.schemas import AspectPreset
from app.timeline.builder import build_timeline_from_events


def _tl(long_fixture):
    return build_timeline_from_events(
        "p", "m", AspectPreset.LONG_FORM_STORY, 1920, 1080, 30.0, long_fixture["events"]
    )


def test_otio_export_round_trips(tmp_path, long_fixture):
    tl = _tl(long_fixture)
    path = otio_export.export_otio(tl, str(long_fixture["path"]), tmp_path / "t.otio")
    reread = otio.adapters.read_from_file(path)
    assert len(reread.tracks[0]) == len(tl.scenes)


def test_fcpxml_export_round_trips_and_is_well_formed_xml(tmp_path, long_fixture):
    import xml.etree.ElementTree as ET

    tl = _tl(long_fixture)
    path = otio_export.export_fcpxml(tl, str(long_fixture["path"]), tmp_path / "t.fcpxml")
    ET.parse(path)  # raises if not well-formed XML
    reread = otio.adapters.read_from_file(path, adapter_name="fcpx_xml")
    assert len(reread.tracks[0]) == len(tl.scenes)


def test_timeline_json_is_valid_and_versioned(tmp_path, long_fixture):
    tl = _tl(long_fixture)
    out = tmp_path / "timeline.json"
    out.write_text(tl.model_dump_json(indent=2))
    data = json.loads(out.read_text())
    assert data["schema_version"] == "1.0.0"
    assert len(data["scenes"]) == len(tl.scenes)


def test_full_and_selective_srt_are_well_formed(tmp_path, long_fixture):
    from app.audio import tts
    from app.render.ffmpeg_render import select_kinetic_caption_words

    tl = _tl(long_fixture)
    full = srt_export.export_full_srt(tl.narration, tmp_path / "full.srt")
    text = Path(full).read_text()
    assert "-->" in text
    assert text.strip().startswith("1\n")

    for nb in tl.narration:
        tts.synthesize_local_fallback(nb, tmp_path / "vo")
    captions = select_kinetic_caption_words(tl.narration)
    assert captions, "fixture narration should yield at least one kinetic caption word"
    sel = srt_export.export_selective_srt(captions, tmp_path / "sel.srt")
    assert "-->" in Path(sel).read_text()
