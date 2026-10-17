"""Import-time INFO logs (avatar registry summary) must reach the container logs."""
from __future__ import annotations

import json
import os
import subprocess
import sys

from conftest import BACKEND_DIR, _OFFLINE_ENV

CUSTOM = json.dumps([
    {"id": "photo_female", "display_name": "Sofia", "character": "F_char",
     "gender": "female", "thumbnail": "photo_female.png", "default": True},
    {"id": "photo_male", "display_name": "Lucas", "character": "M_char",
     "gender": "male", "thumbnail": "photo_male.png"},
])

# Neutralize the developer .env (loaded with override=True) so only our env applies.
_SCRIPT = (
    "import dotenv; dotenv.load_dotenv = lambda *a, **k: False\n"
    "import app\n"
)


def test_avatar_registry_summary_logged_on_app_import():
    env = {**os.environ, **_OFFLINE_ENV,
           "CUSTOM_AVATARS_JSON": CUSTOM, "HIDE_STOCK_AVATARS": "true"}
    proc = subprocess.run([sys.executable, "-c", _SCRIPT], cwd=str(BACKEND_DIR), env=env,
                          capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0, proc.stderr[-2000:]
    assert ("Avatar registry: 2 custom avatar(s) loaded, stock hidden, default=photo_female"
            in proc.stderr), proc.stderr[-2000:]
