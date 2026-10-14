"""Podcast ingest: no local-file fallback, URL ingest disabled by default, SSRF validator."""
from __future__ import annotations

import httpx
import pytest

from services.url_safety import UnsafeURLError, fetch_url, validate_url


def public_resolver(host, port):
    return ["93.184.215.14"]


# ---------------------------------------------------------------------------
# Endpoint behaviour
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("url", [
    "C:\\Windows\\win.ini",
    "/etc/passwd",
    "../../.env",
    "file:///etc/passwd",
    "https://example.com/article",
])
def test_url_ingest_disabled_by_default(client, url):
    r = client.post("/api/podcast/ingest", data={"url": url})
    assert r.status_code == 400
    assert "disabled" in r.json()["detail"].lower()


@pytest.mark.parametrize("url", [
    "C:\\Windows\\win.ini",
    "/etc/passwd",
    "file:///etc/passwd",
    "http://127.0.0.1/",
    "http://169.254.169.254/latest/meta-data/",
    "http://[::ffff:127.0.0.1]/",
    "http://2130706433/",
    "http://user:pw@example.com/",
    "http://example.com:8080/",
])
def test_url_ingest_enabled_still_rejects_unsafe(client, monkeypatch, url):
    monkeypatch.setenv("ENABLE_URL_INGEST", "true")
    r = client.post("/api/podcast/ingest", data={"url": url})
    assert r.status_code == 400, (url, r.status_code, r.text)


def test_local_path_fallback_removed():
    import services.podcast_ingest as ingest_mod

    assert not hasattr(ingest_mod, "ingest"), "path-or-url dispatcher must be gone"
    with pytest.raises(ValueError):
        ingest_mod.ingest_file("/etc/passwd")
    with pytest.raises(ValueError):
        ingest_mod.ingest_file("C:\\Windows\\win.ini")


def test_upload_rejects_unknown_extension(client):
    r = client.post("/api/podcast/ingest", files={"file": ("evil.exe", b"MZ", "application/octet-stream")})
    assert r.status_code == 400


def test_text_upload_still_works(client, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)  # uploads are written under ./data/uploads
    r = client.post("/api/podcast/ingest", files={"file": ("notes.md", b"# Title\nBody text", "text/markdown")})
    assert r.status_code == 200, r.text
    assert r.json()["document"]["title"] == "notes"


def test_upload_size_cap(monkeypatch):
    import asyncio

    from fastapi import HTTPException, UploadFile
    import io

    from security import read_upload_limited

    f = UploadFile(file=io.BytesIO(b"x" * 2048), filename="a.txt")
    with pytest.raises(HTTPException) as exc:
        asyncio.run(read_upload_limited(f, max_bytes=1024))
    assert exc.value.status_code == 413


# ---------------------------------------------------------------------------
# validate_url
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("url", [
    "http://127.0.0.1/",
    "http://127.1/",
    "http://0.0.0.0/",
    "http://10.0.0.5/",
    "http://172.16.3.4/",
    "http://192.168.1.1/",
    "http://100.64.0.1/",
    "http://169.254.169.254/latest/meta-data/",
    "http://[fd00:ec2::254]/",
    "http://[::1]/",
    "http://[fe80::1]/",
    "http://[::ffff:127.0.0.1]/",
    "http://[::ffff:7f00:1]/",
    "http://[::ffff:169.254.169.254]/",
    "http://[::127.0.0.1]/",
    "http://[64:ff9b::a9fe:a9fe]/",
    "http://[2002:a9fe:a9fe::]/",
    "http://[ff02::1]/",
    "http://224.0.0.1/",
    "http://2130706433/",            # decimal 127.0.0.1
    "http://2852039166/",            # decimal 169.254.169.254
    "http://0x7f000001/",            # hex
    "http://0x7f.0x0.0x0.0x1/",
    "http://0177.0.0.1/",            # octal
    "http://017700000001/",
    "http://localhost/",
    "http://foo.localhost/",
    "http://metadata.google.internal/",
    "http://user:pass@example.com/",
    "http://example.com@127.0.0.1/",
    "http://example.com:22/",
    "https://example.com:8443/",
    "ftp://example.com/",
    "file:///etc/passwd",
    "gopher://example.com/",
    "//example.com/",
    "http:///path",
    "http://exa mple.com/",
])
def test_validate_url_rejects(url):
    with pytest.raises(UnsafeURLError):
        validate_url(url, resolver=public_resolver)


@pytest.mark.parametrize("answers", [
    ["10.0.0.1"],
    ["93.184.215.14", "127.0.0.1"],
    ["::ffff:10.0.0.1"],
    ["169.254.169.254"],
    ["fd00:ec2::254"],
])
def test_validate_url_rejects_private_dns_answers(answers):
    with pytest.raises(UnsafeURLError):
        validate_url("https://rebind.example/", resolver=lambda h, p: answers)


@pytest.mark.parametrize("url", [
    "https://example.com/article",
    "http://example.com/",
    "https://example.com:443/x?y=1",
    "http://93.184.215.14/",
])
def test_validate_url_accepts_public(url):
    assert validate_url(url, resolver=public_resolver) == url


def test_url_ingest_flag(monkeypatch):
    from services.url_safety import url_ingest_enabled

    assert url_ingest_enabled() is False
    monkeypatch.setenv("ENABLE_URL_INGEST", "true")
    assert url_ingest_enabled() is True


# ---------------------------------------------------------------------------
# fetch_url: manual redirects + size cap
# ---------------------------------------------------------------------------
def _client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False)


def test_redirect_to_metadata_is_blocked():
    def handler(request):
        return httpx.Response(302, headers={"location": "http://169.254.169.254/latest/meta-data/"})

    with pytest.raises(UnsafeURLError):
        fetch_url("https://example.com/", resolver=public_resolver, client=_client(handler))


def test_redirect_chain_limit():
    def handler(request):
        return httpx.Response(302, headers={"location": "/again"})

    with pytest.raises(UnsafeURLError):
        fetch_url("https://example.com/", resolver=public_resolver, client=_client(handler))


def test_body_cap():
    def handler(request):
        return httpx.Response(200, content=b"x" * (5 * 1024 * 1024 + 10))

    with pytest.raises(UnsafeURLError):
        fetch_url("https://example.com/", resolver=public_resolver, client=_client(handler))


def test_safe_redirect_followed():
    def handler(request):
        if request.url.path == "/start":
            return httpx.Response(301, headers={"location": "https://example.com/final"})
        return httpx.Response(200, text="<html><title>T</title><p>hi</p></html>")

    final, text = fetch_url("https://example.com/start", resolver=public_resolver, client=_client(handler))
    assert final == "https://example.com/final" and "hi" in text
