"""Local dev proxy for the Clara photo-avatar UC1 live test (stdlib only).

  GET /token  -> {region, authToken, iceServers:[{urls,username,credential}]}
  GET /       -> live_clara.html (and any other static file in this dir)

`authToken` is a fresh Speech STS token (10 min lifetime) obtained from
ai-custom-avatar-resource via AAD bearer (local-auth disabled).
"""
from __future__ import annotations

import json
import logging
import mimetypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import requests
from azure.identity import DefaultAzureCredential

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(message)s")
log = logging.getLogger(__name__)

REGION = "swedencentral"
RESOURCE_HOST = "ai-custom-avatar-resource.cognitiveservices.azure.com"
HERE = Path(__file__).parent

_credential = DefaultAzureCredential()


def _aad() -> str:
    return _credential.get_token("https://cognitiveservices.azure.com/.default").token


def _token_payload() -> dict:
    aad = _aad()
    sts = requests.post(
        f"https://{RESOURCE_HOST}/sts/v1.0/issueToken",
        headers={"Authorization": f"Bearer {aad}"}, timeout=15,
    )
    sts.raise_for_status()
    sts_token = sts.text.strip()
    relay = requests.get(
        f"https://{REGION}.tts.speech.microsoft.com/cognitiveservices/avatar/relay/token/v1",
        headers={"Authorization": f"Bearer {sts_token}"}, timeout=15,
    )
    relay.raise_for_status()
    ice = relay.json()
    return {
        "region": REGION,
        "authToken": sts_token,
        "iceServers": [{
            "urls": [ice["Urls"][0]],
            "username": ice["Username"],
            "credential": ice["Password"],
        }],
    }


class Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        path = self.path.split("?", 1)[0]
        if path == "/token":
            try:
                body = json.dumps(_token_payload()).encode()
                self._send(200, body, "application/json")
            except Exception as exc:  # noqa: BLE001
                log.exception("token error")
                self._send(500, str(exc).encode(), "text/plain")
            return
        if path in ("/", ""):
            path = "/live_clara.html"
        candidate = (HERE / path.lstrip("/")).resolve()
        if not str(candidate).startswith(str(HERE.resolve())) or not candidate.is_file():
            self._send(404, b"not found", "text/plain")
            return
        ctype = mimetypes.guess_type(str(candidate))[0] or "application/octet-stream"
        self._send(200, candidate.read_bytes(), ctype)

    def log_message(self, fmt: str, *args) -> None:  # quieter
        log.info(fmt, *args)


if __name__ == "__main__":
    srv = ThreadingHTTPServer(("127.0.0.1", 8765), Handler)
    log.info("listening on http://127.0.0.1:8765")
    srv.serve_forever()
