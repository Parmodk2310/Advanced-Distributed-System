from __future__ import annotations

import os

import pytest


def require_etcd_integration() -> tuple[str, ...]:
    if os.getenv("RUN_ETCD_INTEGRATION") != "1":
        pytest.skip("set RUN_ETCD_INTEGRATION=1 after starting local etcd")
    endpoints = tuple(
        item.strip()
        for item in os.getenv("ETCD_ENDPOINTS", "http://127.0.0.1:2379").split(",")
        if item.strip()
    )
    if not endpoints:
        pytest.fail("ETCD_ENDPOINTS is empty")
    return endpoints
