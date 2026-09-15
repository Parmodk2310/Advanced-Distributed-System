from importlib.metadata import version
from pathlib import Path

import distsys


def test_runtime_version_matches_distribution_metadata() -> None:
    assert distsys.__version__ == version("advanced-distributed-system")


def test_node_coordination_release_is_not_hard_coded() -> None:
    source = Path("src/distsys/node.py").read_text(encoding="utf-8")

    assert 'release="0.5.0"' not in source
    assert "release=__version__" in source
