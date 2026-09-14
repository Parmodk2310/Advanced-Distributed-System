import os
import subprocess
import sys

import pytest

pytestmark = pytest.mark.performance


@pytest.mark.skipif(
    os.getenv("RUN_PERFORMANCE_TESTS") != "1",
    reason="explicit performance opt-in required",
)
def test_quick_task_profile_meets_local_regression_budget():
    subprocess.run(
        [
            sys.executable,
            "scripts/benchmark.py",
            "--profile",
            "quick",
            "--workload",
            "task",
        ],
        check=True,
        env={**os.environ, "PYTHONPATH": "src"},
    )
