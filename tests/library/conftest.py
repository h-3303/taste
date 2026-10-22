import json
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


def pytest_addoption(parser):
    parser.addoption("--run-network", action="store_true", default=False, help="run tests marked 'network'")


def pytest_collection_modifyitems(config, items):
    if config.getoption("--run-network"):
        return
    skip = pytest.mark.skip(reason="needs --run-network")
    for item in items:
        if "network" in item.keywords:
            item.add_marker(skip)


@pytest.fixture
def fixture():
    """fixture("polyhaven/assets.json") -> parsed JSON (or text for non-.json files) from tests/fixtures."""
    def load(name: str):
        p = FIXTURES / name
        return json.loads(p.read_text()) if p.suffix == ".json" else p.read_text()
    return load
