"""Authentication / authorization matrix, /api/me and /ws/voice handshake checks."""
from __future__ import annotations

import pytest
from starlette.websockets import WebSocketDisconnect

from _helpers import ADMIN_OID, OTHER_OID, TENANT

UUID = "0b5f2a7e-1c2d-4e5f-8a9b-0c1d2e3f4a5b"

# (method, path, kwargs) — a sample of gated (cost-bearing / admin) routes.
GATED = [
    ("post", "/api/upload", {"files": {"file": ("a.pptx", b"PK\x03\x04", "application/octet-stream")}}),
    ("post", "/api/decks/upload", {"files": {"file": ("a.pptx", b"PK\x03\x04", "application/octet-stream")}}),
    ("post", "/api/video/ingest", {"files": {"file": ("a.pdf", b"%PDF", "application/pdf")}}),
    ("post", "/api/podcast/ingest", {"files": {"file": ("a.txt", b"hello", "text/plain")}}),
    ("post", "/api/podcast/render", {"json": {}}),
    ("post", f"/api/video/render/{UUID}", {}),
    ("delete", "/api/podcast/library/job-1234abcd", {}),
    ("delete", "/api/video/library/sv-1234abcd", {}),
    ("delete", f"/api/decks/{UUID}", {}),
    ("delete", f"/api/presentations/{UUID}", {}),
    ("post", "/api/video/library/sv-1234abcd/publish", {"json": {"published": True}}),
    ("post", "/api/podcast/library/job-1234abcd/publish", {"json": {"published": True}}),
    ("post", f"/api/decks/{UUID}/publish", {"json": {"published": True}}),
    ("post", "/api/agent/chat", {"json": {"messages": [{"role": "user", "content": "hi"}]}}),
    ("post", "/api/translate", {"json": {"text": "hi", "target_language": "fr-FR"}}),
    ("post", "/api/avatar/batch", {"json": {"presentation_id": UUID}}),
    ("post", "/api/playlists/recommend", {"json": {"topic": "safety"}}),
    ("post", "/api/playlists/pl_0123456789ab/progress", {"json": {"deck_id": UUID, "slide_index": 0}}),
    ("get", "/api/presentations", {}),
    ("get", f"/api/slides/{UUID}", {}),
    ("get", "/api/podcast/voices", {}),
    ("get", "/api/playlists", {}),
    ("post", "/api/search", {"json": {"query": "x"}}),
]


@pytest.mark.parametrize("method,path,kwargs", GATED)
def test_anonymous_is_401(client, easyauth, method, path, kwargs):
    r = getattr(client, method)(path, **kwargs)
    assert r.status_code == 401, (path, r.status_code, r.text)
    assert r.json() == {"detail": "Sign-in required"}


@pytest.mark.parametrize("method,path,kwargs", GATED)
def test_wrong_tenant_is_403(client, easyauth, method, path, kwargs):
    headers = easyauth(oid=ADMIN_OID, tid="00000000-0000-0000-0000-000000000000")
    r = getattr(client, method)(path, headers=headers, **kwargs)
    assert r.status_code == 403, (path, r.status_code, r.text)
    assert r.json() == {"detail": "Not authorized"}


@pytest.mark.parametrize("method,path,kwargs", GATED[:6])
def test_not_allowlisted_is_403(client, easyauth, method, path, kwargs):
    r = getattr(client, method)(path, headers=easyauth(oid=OTHER_OID), **kwargs)
    assert r.status_code == 403
    assert r.json() == {"detail": "Not authorized"}


def test_principal_without_aad_idp_is_anonymous(client, easyauth):
    r = client.get("/api/presentations", headers=easyauth(idp="github"))
    assert r.status_code == 401


def test_garbage_principal_is_anonymous(client, easyauth):
    r = client.get(
        "/api/presentations",
        headers={"X-MS-CLIENT-PRINCIPAL": "not-base64!!", "X-MS-CLIENT-PRINCIPAL-IDP": "aad"},
    )
    assert r.status_code == 401


def test_allowlisted_admin_passes(client, easyauth):
    r = client.get("/api/presentations", headers=easyauth())
    assert r.status_code == 200
    r = client.get("/api/podcast/voices", headers=easyauth())
    assert r.status_code == 200 and len(r.json()) >= 16


def test_empty_tenant_setting_means_nobody_is_admin(client, easyauth, monkeypatch):
    monkeypatch.setenv("AUTH_TENANT_ID", "")
    assert client.get("/api/presentations", headers=easyauth()).status_code == 403


def test_disabled_mode_is_admin(client):
    r = client.get("/api/presentations")
    assert r.status_code == 200


def test_anonymous_routes_stay_open(client, easyauth):
    assert client.get("/api/health").status_code == 200
    assert client.get("/api/me").status_code == 200
    assert client.get("/api/avatars").status_code == 200
    assert client.get("/api/video/library").status_code == 200
    assert client.get("/api/podcast/library").status_code == 200
    assert client.get("/api/decks").status_code == 200


# ---------------------------------------------------------------------------
# /api/me
# ---------------------------------------------------------------------------
def test_me_anonymous(client, easyauth):
    assert client.get("/api/me").json() == {
        "authenticated": False, "is_admin": False, "name": None, "auth_mode": "easyauth",
    }


def test_me_signed_in_not_admin(client, easyauth):
    body = client.get("/api/me", headers=easyauth(oid=OTHER_OID, name="Someone")).json()
    assert body == {"authenticated": True, "is_admin": False, "name": "Someone", "auth_mode": "easyauth"}


def test_me_admin(client, easyauth):
    body = client.get("/api/me", headers=easyauth()).json()
    assert body == {"authenticated": True, "is_admin": True, "name": "Test Admin", "auth_mode": "easyauth"}


def test_me_disabled(client):
    body = client.get("/api/me").json()
    assert body["auth_mode"] == "disabled" and body["is_admin"] is True and body["authenticated"] is True


# ---------------------------------------------------------------------------
# /ws/voice — rejected before accept()
# ---------------------------------------------------------------------------
def _ws_close_code(client, headers=None):
    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect("/ws/voice", headers=headers or {}):
            pass
    return exc.value.code


def test_ws_anonymous_rejected(client, easyauth):
    assert _ws_close_code(client, {"origin": "http://testserver"}) == 4401


def test_ws_not_admin_rejected(client, easyauth):
    headers = {**easyauth(oid=OTHER_OID), "origin": "http://testserver"}
    assert _ws_close_code(client, headers) == 4403


def test_ws_bad_origin_rejected(client, easyauth):
    headers = {**easyauth(), "origin": "https://evil.example"}
    assert _ws_close_code(client, headers) == 4403


def test_ws_missing_origin_rejected_in_easyauth(client, easyauth):
    assert _ws_close_code(client, easyauth()) == 4403


def test_ws_allowed_origins_list(client, easyauth, monkeypatch):
    monkeypatch.setenv("ALLOWED_ORIGINS", "https://app.example")
    headers = {**easyauth(), "origin": "https://evil.example"}
    assert _ws_close_code(client, headers) == 4403


def test_origin_allowlist_is_additive(monkeypatch):
    from security import origin_allowed

    monkeypatch.setenv("AUTH_MODE", "easyauth")
    monkeypatch.setenv("ALLOWED_ORIGINS", "https://teams.example")
    assert origin_allowed({"origin": "https://app.example", "host": "app.example"})
    assert origin_allowed({"origin": "https://teams.example", "host": "app.example"})
    assert not origin_allowed({"origin": "https://evil.example", "host": "app.example"})


def test_ws_concurrency_cap(client, easyauth, monkeypatch, app_module):
    from security import VOICE_SESSIONS

    monkeypatch.setenv("MAX_VOICE_SESSIONS", "1")
    monkeypatch.setattr(app_module, "config", object())
    assert VOICE_SESSIONS.try_acquire()
    headers = {**easyauth(), "origin": "http://testserver"}
    with client.websocket_connect("/ws/voice", headers=headers) as ws:
        with pytest.raises(WebSocketDisconnect) as exc:
            ws.receive_text()
    assert exc.value.code == 1013


def test_origin_helper_same_origin_and_dev(monkeypatch):
    from security import origin_allowed

    monkeypatch.setenv("AUTH_MODE", "easyauth")
    assert origin_allowed({"origin": "https://app.example", "host": "app.example"})
    assert not origin_allowed({"origin": "https://evil.example", "host": "app.example"})
    assert not origin_allowed({"host": "app.example"})
    monkeypatch.setenv("AUTH_MODE", "disabled")
    assert origin_allowed({"origin": "http://localhost:5173", "host": "127.0.0.1:8000"})
    assert not origin_allowed({"origin": "https://evil.example", "host": "127.0.0.1:8000"})


def test_token_route_removed(client):
    r = client.get("/api/avatar/token")
    assert r.status_code == 404
    import services.avatar as avatar_mod

    assert not hasattr(avatar_mod, "get_speech_token")
    assert not any(getattr(rt, "path", "") == "/api/avatar/token" for rt in client.app.routes)


def test_user_id_comes_from_principal(monkeypatch):
    from auth import principal_from_headers
    from _helpers import principal_headers

    monkeypatch.setenv("AUTH_MODE", "easyauth")
    monkeypatch.setenv("AUTH_TENANT_ID", TENANT)
    monkeypatch.setenv("ALLOWED_OBJECT_IDS", ADMIN_OID)
    hdrs = {k.lower(): v for k, v in principal_headers().items()}
    assert principal_from_headers(hdrs).user_id == ADMIN_OID
    monkeypatch.setenv("AUTH_MODE", "disabled")
    assert principal_from_headers({}).user_id == "local-dev"


def test_admin_client_ip_diagnostic_is_admin_only(client, easyauth):
    assert client.get("/api/admin/client-ip").status_code == 401
    r = client.get("/api/admin/client-ip", headers={**easyauth(), "x-forwarded-for": "1.2.3.4, 203.0.113.9"})
    assert r.status_code == 200 and r.json()["client_ip"] == "203.0.113.9"
