from unittest.mock import patch

from sideclaw.security.network import (
    contains_internal_url,
    validate_resolved_url,
    validate_url_target,
)


def _fake_getaddrinfo_public(host, port, family=0, type=0, proto=0, flags=0):
    return [(2, 1, 6, "", ("93.184.216.34", 0))]


def _fake_getaddrinfo_private(host, port, family=0, type=0, proto=0, flags=0):
    return [(2, 1, 6, "", ("192.168.1.1", 0))]


def _fake_getaddrinfo_localhost(host, port, family=0, type=0, proto=0, flags=0):
    return [(2, 1, 6, "", ("127.0.0.1", 0))]


def _fake_getaddrinfo_metadata(host, port, family=0, type=0, proto=0, flags=0):
    return [(2, 1, 6, "", ("169.254.169.254", 0))]


def _fake_getaddrinfo_10x(host, port, family=0, type=0, proto=0, flags=0):
    return [(2, 1, 6, "", ("10.0.0.1", 0))]


def _fake_getaddrinfo_172(host, port, family=0, type=0, proto=0, flags=0):
    return [(2, 1, 6, "", ("172.16.5.10", 0))]


def _fake_getaddrinfo_ipv6_loopback(host, port, family=0, type=0, proto=0, flags=0):
    return [(10, 1, 6, "", ("::1", 0, 0, 0))]


@patch("sideclaw.security.network.socket.getaddrinfo", _fake_getaddrinfo_public)
def test_allows_public_ip():
    ok, err = validate_url_target("https://example.com")
    assert ok is True
    assert err == ""


@patch("sideclaw.security.network.socket.getaddrinfo", _fake_getaddrinfo_localhost)
def test_blocks_localhost():
    ok, err = validate_url_target("http://localhost/admin")
    assert ok is False
    assert "private/reserved" in err


@patch("sideclaw.security.network.socket.getaddrinfo", _fake_getaddrinfo_private)
def test_blocks_192_168():
    ok, err = validate_url_target("http://192.168.1.1/")
    assert ok is False
    assert "private/reserved" in err


@patch("sideclaw.security.network.socket.getaddrinfo", _fake_getaddrinfo_10x)
def test_blocks_10x():
    ok, err = validate_url_target("http://internal.corp/api")
    assert ok is False
    assert "private/reserved" in err


@patch("sideclaw.security.network.socket.getaddrinfo", _fake_getaddrinfo_172)
def test_blocks_172_16():
    ok, err = validate_url_target("http://172.16.5.10/secret")
    assert ok is False
    assert "private/reserved" in err


@patch("sideclaw.security.network.socket.getaddrinfo", _fake_getaddrinfo_metadata)
def test_blocks_metadata_endpoint():
    ok, err = validate_url_target("http://169.254.169.254/latest/meta-data/")
    assert ok is False
    assert "private/reserved" in err


@patch("sideclaw.security.network.socket.getaddrinfo", _fake_getaddrinfo_ipv6_loopback)
def test_blocks_ipv6_loopback():
    ok, err = validate_url_target("http://[::1]/")
    assert ok is False
    assert "private/reserved" in err


def test_rejects_non_http_scheme():
    ok, err = validate_url_target("ftp://example.com/file")
    assert ok is False
    assert "Only http/https" in err


@patch("sideclaw.security.network.socket.getaddrinfo", _fake_getaddrinfo_private)
def test_validate_resolved_url_blocks_redirect_to_private():
    ok, err = validate_resolved_url("http://evil.com/redirect")
    assert ok is False
    assert "private/reserved" in err


@patch("sideclaw.security.network.socket.getaddrinfo", _fake_getaddrinfo_localhost)
def test_contains_internal_url_finds_curl():
    assert contains_internal_url("curl http://localhost:8080/admin") is True


@patch("sideclaw.security.network.socket.getaddrinfo", _fake_getaddrinfo_metadata)
def test_contains_internal_url_finds_wget():
    assert contains_internal_url("wget http://169.254.169.254/latest/meta-data/") is True


@patch("sideclaw.security.network.socket.getaddrinfo", _fake_getaddrinfo_public)
def test_contains_internal_url_allows_public():
    assert contains_internal_url("curl https://example.com/api") is False


def test_contains_internal_url_no_urls():
    assert contains_internal_url("echo hello world") is False
