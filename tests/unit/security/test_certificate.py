from distsys.security.certificate import dns_sans, ip_sans


def test_san_extractors():
    cert = {"subjectAltName": (("DNS", "node-1"), ("DNS", "other"), ("IP Address", "127.0.0.1"))}
    assert dns_sans(cert) == frozenset({"node-1", "other"})
    assert ip_sans(cert) == frozenset({"127.0.0.1"})
