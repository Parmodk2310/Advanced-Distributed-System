import os
import subprocess
import sys

import pytest

pytestmark = pytest.mark.chaos


@pytest.mark.skipif(os.getenv("RUN_CHAOS_TESTS") != "1", reason="explicit chaos opt-in required")
@pytest.mark.parametrize("scenario", ["network-delay", "partition", "etcd-outage", "node-kill"])
def test_guarded_phase6_scenario_cleans_up(scenario: str):
    subprocess.run(
        [sys.executable, "scripts/chaos.py", scenario, "--target", "node-1", "--max-seconds", "30"],
        check=True,
        env={**os.environ, "PYTHONPATH": "src", "RUN_CHAOS_TESTS": "1"},
    )
