import hashlib

import pytest

from distsys.compute.errors import TaskValidationError
from distsys.compute.tasks import aggregate_task, hash_task, sort_task


def test_hash_task_returns_deterministic_sha256_digest():
    result = hash_task({"data": "hello", "rounds": 1})
    assert result == {
        "algorithm": "sha256",
        "digest": hashlib.sha256(b"hello").hexdigest(),
        "rounds": 1,
    }


def test_hash_task_rejects_invalid_rounds():
    with pytest.raises(TaskValidationError, match="rounds"):
        hash_task({"data": "hello", "rounds": 0})


def test_sort_task_sorts_numeric_values_without_mutating_contract():
    assert sort_task({"values": [8, 3, 1, 7, 2]}) == {
        "values": [1, 2, 3, 7, 8],
        "count": 5,
    }


def test_sort_task_rejects_non_numeric_values():
    with pytest.raises(TaskValidationError, match="numbers"):
        sort_task({"values": [1, "2"]})


def test_aggregate_task_returns_basic_statistics():
    assert aggregate_task({"values": [1, 2, 3, 4]}) == {
        "count": 4,
        "sum": 10.0,
        "min": 1.0,
        "max": 4.0,
        "mean": 2.5,
    }


def test_aggregate_task_rejects_empty_values():
    with pytest.raises(TaskValidationError, match="non-empty"):
        aggregate_task({"values": []})


@pytest.mark.asyncio
async def test_whoami_task_reports_bound_node_identity():
    from distsys.compute.tasks import make_whoami_task

    task = make_whoami_task("node-2")
    assert await task({}) == {"node_id": "node-2"}
