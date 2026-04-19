"""End-to-end API tests for UC1 Learning Hub.

Drives a live backend via BASE_URL. The `uploaded_decks` session fixture in
conftest.py uploads all 6 test PPTX files once and tears them down at the end.
"""
from __future__ import annotations

import uuid
from pathlib import Path

import httpx
import pytest

from conftest import FIXTURE_DIR, FIXTURES


# ---------------------------------------------------------------------------
# 1. Smoke / health
# ---------------------------------------------------------------------------
def test_health(client: httpx.Client) -> None:
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json().get("status") == "ok"


# ---------------------------------------------------------------------------
# 2. Upload validation
# ---------------------------------------------------------------------------
def test_upload_rejects_non_pptx(client: httpx.Client) -> None:
    r = client.post(
        "/api/uc1/upload",
        files={"file": ("notes.txt", b"hello world", "text/plain")},
    )
    assert r.status_code == 400
    assert "pptx" in r.text.lower()


def test_upload_rejects_corrupt_pptx(client: httpx.Client) -> None:
    # Bytes that start with 'PK' but aren't a real ZIP
    r = client.post(
        "/api/uc1/upload",
        files={"file": ("bad.pptx", b"PK\x03\x04 corrupted bytes here", "application/octet-stream")},
    )
    assert r.status_code == 400


def test_upload_indexes_all_slides(uploaded_decks) -> None:
    """Every uploaded deck indexed each of its 6 slides (title + 5 content)."""
    assert len(uploaded_decks) == 6
    for filename, resp in uploaded_decks.items():
        assert resp["slide_count"] == 6, f"{filename} slide count != 6"
        assert resp["indexed_slides"] == 6, f"{filename} indexed != 6"
        assert resp["deck_id"]


# ---------------------------------------------------------------------------
# 3. List / Get / 404
# ---------------------------------------------------------------------------
def test_list_decks_shows_all_uploaded(client: httpx.Client, uploaded_decks) -> None:
    r = client.get("/api/uc1/decks")
    assert r.status_code == 200
    decks = r.json()
    assert isinstance(decks, list)
    listed_ids = {d["deck_id"] for d in decks}
    for resp in uploaded_decks.values():
        assert resp["deck_id"] in listed_ids
    # Verify metadata shape on at least one entry
    sample = next(d for d in decks if d["deck_id"] in {r["deck_id"] for r in uploaded_decks.values()})
    for key in ("deck_id", "title", "slide_count", "language", "uploaded_at", "tags"):
        assert key in sample


def test_get_deck_detail_has_slides(client: httpx.Client, uploaded_decks) -> None:
    for resp in uploaded_decks.values():
        r = client.get(f"/api/uc1/decks/{resp['deck_id']}")
        assert r.status_code == 200
        detail = r.json()
        assert detail["deck_id"] == resp["deck_id"]
        assert len(detail["slides"]) == 6
        for slide in detail["slides"]:
            assert "index" in slide and "title" in slide
            assert slide.get("image_url"), "image_url should be populated"


def test_get_missing_deck_404(client: httpx.Client) -> None:
    r = client.get(f"/api/uc1/decks/{uuid.uuid4()}")
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# 4. Cross-deck search — topic disambiguation
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("filename,language,query,expected_title_substr", FIXTURES)
def test_search_topic_returns_correct_deck(
    client: httpx.Client,
    uploaded_decks,
    filename: str,
    language: str,
    query: str,
    expected_title_substr: str,
) -> None:
    r = client.post("/api/uc1/learn/search", json={"query": query, "top_k": 3})
    assert r.status_code == 200
    results = r.json()["results"]
    assert results, f"no results for query '{query}'"
    top = results[0]
    assert expected_title_substr in top["deck_title"], (
        f"top hit for '{query}' was '{top['deck_title']}' — expected substring '{expected_title_substr}'"
    )


# ---------------------------------------------------------------------------
# 5. Language filter
# ---------------------------------------------------------------------------
def test_search_french_filter_returns_french_deck(client: httpx.Client, uploaded_decks) -> None:
    r = client.post(
        "/api/uc1/learn/search",
        json={"query": "énergie hydrogène nucléaire", "top_k": 5, "language": "fr-FR"},
    )
    assert r.status_code == 200
    results = r.json()["results"]
    assert results
    for hit in results:
        assert "transition-energetique" in hit["deck_title"]


def test_search_spanish_filter_returns_spanish_deck(client: httpx.Client, uploaded_decks) -> None:
    r = client.post(
        "/api/uc1/learn/search",
        json={"query": "innovación gemelos digitales robótica", "top_k": 5, "language": "es-ES"},
    )
    assert r.status_code == 200
    results = r.json()["results"]
    assert results
    for hit in results:
        assert "innovacion-industrial" in hit["deck_title"]


# ---------------------------------------------------------------------------
# 6. Search edge cases
# ---------------------------------------------------------------------------
def test_search_empty_query_400(client: httpx.Client) -> None:
    r = client.post("/api/uc1/learn/search", json={"query": "   ", "top_k": 5})
    assert r.status_code == 400


def test_search_top_k_respected(client: httpx.Client, uploaded_decks) -> None:
    r = client.post("/api/uc1/learn/search", json={"query": "carbon emissions", "top_k": 2})
    assert r.status_code == 200
    results = r.json()["results"]
    assert len(results) <= 2


# ---------------------------------------------------------------------------
# 7. Delete — removed from list + search
# ---------------------------------------------------------------------------
def test_delete_deck_removes_from_list_and_search(client: httpx.Client) -> None:
    """Upload a dedicated throw-away deck, delete it, verify it's gone."""
    import time

    path = FIXTURE_DIR / "climate-action.pptx"
    with path.open("rb") as fh:
        r = client.post(
            "/api/uc1/upload",
            files={"file": ("delete-me.pptx", fh, "application/vnd.openxmlformats-officedocument.presentationml.presentation")},
            data={"language": "en-US"},
        )
    assert r.status_code == 200
    deck_id = r.json()["deck_id"]

    # Confirm it's there
    r_list = client.get("/api/uc1/decks")
    assert deck_id in {d["deck_id"] for d in r_list.json()}

    # Delete
    r_del = client.delete(f"/api/uc1/decks/{deck_id}")
    assert r_del.status_code == 200

    # Gone from list
    r_list2 = client.get("/api/uc1/decks")
    assert deck_id not in {d["deck_id"] for d in r_list2.json()}

    # Detail → 404
    r_get = client.get(f"/api/uc1/decks/{deck_id}")
    assert r_get.status_code == 404

    # AI Search deletion is near-real-time but not strictly immediate. Retry a few times.
    for _ in range(20):
        r_search = client.post("/api/uc1/learn/search", json={"query": "net zero emissions", "top_k": 10})
        assert r_search.status_code == 200
        if deck_id not in {h["deck_id"] for h in r_search.json()["results"]}:
            return
        time.sleep(3)
    pytest.fail(f"Deck {deck_id} still in search results after delete")
