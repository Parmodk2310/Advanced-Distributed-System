import pytest

from distsys.chaos.routing import peer_routing_enabled, resolve_peer_endpoint


def test_peer_routing_enabled_requires_opt_in_and_mapping(monkeypatch):
    monkeypatch.delenv("RUN_CHAOS_TESTS", raising=False)
    monkeypatch.delenv("PHASE6_PEER_PROXY_MAP", raising=False)
    assert peer_routing_enabled() is False

    monkeypatch.setenv("RUN_CHAOS_TESTS", "1")
    assert peer_routing_enabled() is False

    monkeypatch.setenv("PHASE6_PEER_PROXY_MAP", "node-1=127.0.0.1:19101")
    assert peer_routing_enabled() is True


def test_proxy_map_is_disabled_without_chaos_opt_in(monkeypatch):
    monkeypatch.delenv("RUN_CHAOS_TESTS", raising=False)
    monkeypatch.setenv("PHASE6_PEER_PROXY_MAP", "node-1=127.0.0.1:19101")
    assert resolve_peer_endpoint("node-1", "127.0.0.1", 18001) == ("127.0.0.1", 18001)


def test_proxy_map_rewrites_only_named_peer(monkeypatch):
    monkeypatch.setenv("RUN_CHAOS_TESTS", "1")
    monkeypatch.setenv("PHASE6_PEER_PROXY_MAP", "node-0=127.0.0.1:19100,node-1=127.0.0.1:19101")
    assert resolve_peer_endpoint("node-1", "127.0.0.1", 18001) == ("127.0.0.1", 19101)
    assert resolve_peer_endpoint("node-x", "127.0.0.1", 18888) == ("127.0.0.1", 18888)


def test_bad_proxy_map_fails_closed(monkeypatch):
    monkeypatch.setenv("RUN_CHAOS_TESTS", "1")
    monkeypatch.setenv("PHASE6_PEER_PROXY_MAP", "node-1=not-a-host-port")
    with pytest.raises(ValueError):
        resolve_peer_endpoint("node-1", "127.0.0.1", 18001)
