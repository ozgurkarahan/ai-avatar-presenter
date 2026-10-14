"""Test helpers shared by the backend test modules."""
from __future__ import annotations

import base64
import json

TENANT = "11111111-2222-3333-4444-555555555555"
ADMIN_OID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
OTHER_OID = "99999999-8888-7777-6666-555555555555"



def principal_headers(oid: str = ADMIN_OID, tid: str = TENANT, idp: str = "aad", name: str = "Test Admin") -> dict:
    payload = {
        "auth_typ": "aad",
        "claims": [
            {"typ": "http://schemas.microsoft.com/identity/claims/objectidentifier", "val": oid},
            {"typ": "http://schemas.microsoft.com/identity/claims/tenantid", "val": tid},
            {"typ": "name", "val": name},
        ],
    }
    raw = base64.b64encode(json.dumps(payload).encode()).decode()
    return {"X-MS-CLIENT-PRINCIPAL": raw, "X-MS-CLIENT-PRINCIPAL-IDP": idp}
