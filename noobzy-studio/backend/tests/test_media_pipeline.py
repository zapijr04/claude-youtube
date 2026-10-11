from pathlib import Path

from app.media import ffprobe_util, proxy, scenes


def test_probe_detects_real_codec_duration_fps(long_fixture):
    info = ffprobe_util.probe(long_fixture["path"])
    assert info["codec"] == "h264"
    assert info["width"] == 1920 and info["height"] == 1080
    assert info["fps"] == 30.0
    assert abs(info["duration_sec"] - long_fixture["total_duration_sec"]) < 0.5
    assert info["has_audio"] is True


def test_scene_cut_detection_finds_most_true_boundaries(long_fixture):
    cuts = scenes.detect_scene_cuts(long_fixture["path"], threshold=0.3)
    ground_truth = [e["at_sec"] for e in long_fixture["events"] if e["kind"] not in ("end",) and e["at_sec"] > 0]
    found = 0
    for gt in ground_truth:
        if any(abs(gt - c) < 1.0 for c in cuts):
            found += 1
    # Real detector on real pixel differences -- expect most (not literally
    # all; a dark-to-dark transition is a known miss) of the true cuts.
    assert found >= len(ground_truth) - 2


def test_thumbnails_and_waveform_are_real_files(tmp_path, long_fixture):
    thumbs = proxy.generate_thumbnails(long_fixture["path"], tmp_path / "thumbs", count=3)
    assert len(thumbs) == 3
    for t in thumbs:
        assert Path(t).stat().st_size > 500
    wave = proxy.generate_waveform(long_fixture["path"], tmp_path / "wave.png")
    assert Path(wave).stat().st_size > 500
