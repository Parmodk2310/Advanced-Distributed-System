import pytest

from distsys.security.identity import TlsPeerIdentityError, verify_node_identity


def test_verify_node_identity_accepts_matching_dns_san():
    cert = {"subjectAltName": (("DNS", "node-1"), ("IP Address", "127.0.0.1"))}
    verify_node_identity(cert, "node-1")


def test_verify_node_identity_rejects_wrong_dns_san():
    cert = {"subjectAltName": (("DNS", "node-2"),)}
    with pytest.raises(TlsPeerIdentityError):
        verify_node_identity(cert, "node-1")


def test_verify_node_identity_does_not_fallback_to_common_name():
    cert = {"subject": ((("commonName", "node-1"),),), "subjectAltName": ()}
    with pytest.raises(TlsPeerIdentityError):
        verify_node_identity(cert, "node-1")
