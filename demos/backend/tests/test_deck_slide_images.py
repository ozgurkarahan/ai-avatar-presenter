"""Catalog deck slide images are written where GET /api/slides serves them.

Regression: routers/decks.py wrote PNGs to ``slides_cache/`` while app.py
serves (and caches blob downloads in) ``data/slides/``; without Blob Storage
(local dev, or a failed blob upload) every catalog slide image was a 404.
"""
from __future__ import annotations

import io
import shutil
import uuid
import zipfile

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


def test_decks_and_app_share_the_slide_directory(app_module):
    import routers.decks as decks

    assert decks.SLIDES_DIR.resolve() == app_module.SLIDES_DIR.resolve()


def test_uploaded_deck_slide_image_is_served_without_blob(client, easyauth, monkeypatch):
    import routers.decks as decks
    from services.pptx_parser import PresentationData, SlideData

    deck_id = str(uuid.uuid4())
    pres = PresentationData(
        id=deck_id, filename="Deck.pptx", slide_count=1,
        slides=[SlideData(index=0, title="T", body="B", notes="N")],
        slide_images=[(0, PNG)],
    )
    monkeypatch.setattr(decks, "parse_pptx", lambda *a, **k: pres)
    monkeypatch.setattr(decks, "_store", lambda cfg: None)
    monkeypatch.setattr(decks, "get_deck_search", lambda *a, **k: None)
    monkeypatch.setattr(decks, "get_openai_client", lambda cfg: object())
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("[Content_Types].xml", "<Types/>")
    try:
        r = client.post("/api/decks/upload", headers=easyauth(),
                        files={"file": ("Deck.pptx", buf.getvalue(), "application/octet-stream")})
        assert r.status_code == 200, r.text
        img = client.get(f"/api/slides/{deck_id}/0.png", headers=easyauth())
        assert img.status_code == 200
        assert img.content == PNG
    finally:
        shutil.rmtree(decks.SLIDES_DIR / deck_id, ignore_errors=True)
