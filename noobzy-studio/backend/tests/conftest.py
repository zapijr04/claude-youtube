import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tests.fixtures.make_fixture import build_long_fixture, build_short_fixture

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "generated"


@pytest.fixture(scope="session")
def long_fixture() -> dict:
    path = build_long_fixture(FIXTURES_DIR)
    events = json.loads(path.with_suffix("").with_suffix(".events.json").read_text()) \
        if False else json.loads((FIXTURES_DIR / "fixture_long.events.json").read_text())
    return {"path": path, "events": events["events"], "total_duration_sec": events["total_duration_sec"]}


@pytest.fixture(scope="session")
def short_fixture() -> dict:
    path = build_short_fixture(FIXTURES_DIR)
    events = json.loads((FIXTURES_DIR / "fixture_short.events.json").read_text())
    return {"path": path, "events": events["events"], "total_duration_sec": events["total_duration_sec"]}
