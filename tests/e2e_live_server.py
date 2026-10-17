"""Local backend launcher for the LIVE end-to-end suite (tests/e2e-live.spec.ts).

Test-only. Runs the real FastAPI app against real Azure Speech / Voice Live /
OpenAI (from demos/backend/.env) with two local substitutions:

* Cosmos DB is replaced by an in-memory container (no Cosmos locally). The real
  ``PresentationStore`` code paths (publish, live demo, durable demo quota with
  etags) run unchanged on top of it. Blob Storage stays unavailable, so slide
  images are served from local disk like in local dev.
* Easy Auth is emulated: ``AUTH_MODE=easyauth`` with a fake tenant/object id.
  demos/frontend/vite.e2e-live.config.ts plays the Container Apps front door:
  the admin Vite instance injects the ``X-MS-CLIENT-PRINCIPAL`` headers
  (``--print-principal``) on /api and /ws, the anonymous instance injects none.

Usage: python tests/e2e_live_server.py [--port 8000]
"""
from __future__ import annotations

import argparse
import copy
import os
import re
import sys
import threading
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "demos" / "backend"

E2E_TENANT = "00000000-0000-0000-0000-00000000e2e0"
E2E_ADMIN_OID = "00000000-0000-0000-0000-0000000ad111"


class _FakeContainer:
    """Tiny in-memory stand-in for an azure.cosmos ContainerProxy."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._items: dict[str, dict] = {}

    def _nf(self):
        from azure.cosmos import exceptions as ce
        return ce.CosmosResourceNotFoundError(message="not found")

    def read(self):
        return {}

    def read_item(self, item, partition_key=None):
        with self._lock:
            doc = self._items.get(item)
            if doc is None:
                raise self._nf()
            return copy.deepcopy(doc)

    def upsert_item(self, body):
        with self._lock:
            doc = copy.deepcopy(body)
            doc["_etag"] = uuid.uuid4().hex
            self._items[doc["id"]] = doc
            return copy.deepcopy(doc)

    def create_item(self, body):
        from azure.cosmos import exceptions as ce
        with self._lock:
            if body["id"] in self._items:
                raise ce.CosmosResourceExistsError(message="exists")
            doc = copy.deepcopy(body)
            doc["_etag"] = uuid.uuid4().hex
            self._items[doc["id"]] = doc
            return copy.deepcopy(doc)

    def replace_item(self, item, body, etag=None, match_condition=None):
        from azure.cosmos import exceptions as ce
        with self._lock:
            cur = self._items.get(item)
            if cur is None:
                raise self._nf()
            if etag is not None and cur.get("_etag") != etag:
                raise ce.CosmosAccessConditionFailedError(message="etag mismatch")
            doc = copy.deepcopy(body)
            doc["_etag"] = uuid.uuid4().hex
            self._items[item] = doc
            return copy.deepcopy(doc)

    def delete_item(self, item, partition_key=None):
        with self._lock:
            if item not in self._items:
                raise self._nf()
            del self._items[item]

    def query_items(self, query, parameters=None, enable_cross_partition_query=None, **_):
        m = re.search(r"c\.source\s*=\s*'([a-z_-]+)'", query)
        with self._lock:
            docs = [copy.deepcopy(d) for d in self._items.values()]
        if m:
            docs = [d for d in docs if d.get("source") == m.group(1)]
        if parameters and "s.deck_id" in query:
            deck = parameters[0]["value"]
            docs = [d for d in docs if any(isinstance(s, dict) and s.get("deck_id") == deck for s in d.get("steps") or [])]
        return iter(docs)


_PRESENTATIONS = _FakeContainer()
_PROGRESS = _FakeContainer()


def _install_fake_cosmos() -> None:
    from services import storage

    def _ensure_init(self) -> bool:
        self._initialised = True
        self._cosmos_container = _PRESENTATIONS
        self._progress_container = _PROGRESS
        self._blob_client = None
        return True

    storage.PresentationStore._ensure_init = _ensure_init


def _prepend_tools_to_path() -> None:
    extra = [p for p in (os.environ.get("OZ_RADIO_E2E_TOOL_DIRS") or "").split(os.pathsep) if p]
    if extra:
        os.environ["PATH"] = os.pathsep.join(extra + [os.environ.get("PATH", "")])


def admin_principal_b64() -> str:
    """The X-MS-CLIENT-PRINCIPAL value Easy Auth would inject for the E2E admin."""
    import base64
    import json
    claims = {
        "auth_typ": "aad",
        "claims": [
            {"typ": "http://schemas.microsoft.com/identity/claims/objectidentifier", "val": E2E_ADMIN_OID},
            {"typ": "http://schemas.microsoft.com/identity/claims/tenantid", "val": E2E_TENANT},
            {"typ": "name", "val": "E2E Admin"},
        ],
    }
    return base64.b64encode(json.dumps(claims).encode()).decode()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--print-principal", action="store_true",
                    help="print the admin X-MS-CLIENT-PRINCIPAL value (for vite.e2e-live.config.ts) and exit")
    args = ap.parse_args()
    if args.print_principal:
        print(admin_principal_b64())
        return

    os.chdir(BACKEND)
    sys.path.insert(0, str(BACKEND))
    _prepend_tools_to_path()
    os.environ["AUTH_MODE"] = "easyauth"
    os.environ["AUTH_TENANT_ID"] = E2E_TENANT
    os.environ["ALLOWED_OBJECT_IDS"] = E2E_ADMIN_OID

    import config  # noqa: F401  (loads demos/backend/.env with override=True)

    # .env must not switch auth off for this run (it would make everyone admin).
    if os.environ.get("AUTH_MODE", "").lower() == "disabled":
        raise SystemExit("demos/backend/.env sets AUTH_MODE=disabled; the live E2E needs easyauth emulation")
    os.environ["AUTH_TENANT_ID"] = E2E_TENANT
    os.environ["ALLOWED_OBJECT_IDS"] = E2E_ADMIN_OID
    # Repeated local runs from one IP: keep the per-session caps under test
    # (2 questions, 5 min) but allow more sessions/questions per day.
    os.environ.setdefault("DEMO_DAILY_SESSIONS_PER_IP", "30")
    os.environ.setdefault("DEMO_QA_DAILY_PER_IP", "30")

    _install_fake_cosmos()

    import uvicorn
    uvicorn.run("app:app", host="127.0.0.1", port=args.port, log_level="info")


if __name__ == "__main__":
    main()
