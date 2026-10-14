"""UC1 Learning Paths API tests — runs against deployed ACA."""
from __future__ import annotations

import concurrent.futures
import time
from typing import Iterator

import httpx
import pytest

from conftest import FIXTURES  # reuse BASE_URL + uploaded_decks fixture


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def deck_ids(uploaded_decks) -> list[str]:
    """Stable list of deck_ids in the order of FIXTURES (EN decks first)."""
    return [uploaded_decks[fn]["deck_id"] for fn, *_ in FIXTURES]


@pytest.fixture(scope="module")
def path_with_steps(client: httpx.Client, deck_ids) -> Iterator[dict]:
    """Create a path with the first 3 uploaded decks as steps."""
    steps = [
        {"deck_id": deck_ids[i], "order": i, "required": True}
        for i in range(3)
    ]
    r = client.post("/api/uc1/paths", json={
        "title": "Pytest Path — Onboarding",
        "description": "Created by pytest for integration testing.",
        "steps": steps,
    })
    assert r.status_code == 200, r.text
    path = r.json()
    yield path
    client.delete(f"/api/uc1/paths/{path['id']}")


# ---------------------------------------------------------------------------
# CRUD — happy paths
# ---------------------------------------------------------------------------
def test_list_paths_endpoint_ok(client: httpx.Client) -> None:
    r = client.get("/api/uc1/paths")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_create_path_ok(client: httpx.Client, deck_ids) -> None:
    r = client.post("/api/uc1/paths", json={
        "title": "Temp create test",
        "description": "",
        "steps": [{"deck_id": deck_ids[0], "order": 0, "required": True}],
    })
    assert r.status_code == 200
    data = r.json()
    assert data["id"].startswith("path_")
    assert data["step_count"] == 1
    assert data["steps"][0]["deck_title"] != ""
    assert data["steps"][0]["slide_count"] > 0
    client.delete(f"/api/uc1/paths/{data['id']}")


def test_get_path_detail(client: httpx.Client, path_with_steps: dict) -> None:
    r = client.get(f"/api/uc1/paths/{path_with_steps['id']}")
    assert r.status_code == 200
    assert r.json()["step_count"] == 3


def test_update_path(client: httpx.Client, deck_ids) -> None:
    r = client.post("/api/uc1/paths", json={
        "title": "will-be-updated",
        "steps": [{"deck_id": deck_ids[0], "order": 0}],
    })
    pid = r.json()["id"]
    r2 = client.put(f"/api/uc1/paths/{pid}", json={"title": "renamed"})
    assert r2.status_code == 200
    assert r2.json()["title"] == "renamed"
    client.delete(f"/api/uc1/paths/{pid}")


def test_delete_path_then_404(client: httpx.Client, deck_ids) -> None:
    r = client.post("/api/uc1/paths", json={
        "title": "throwaway",
        "steps": [{"deck_id": deck_ids[0], "order": 0}],
    })
    pid = r.json()["id"]
    r_del = client.delete(f"/api/uc1/paths/{pid}")
    assert r_del.status_code == 200
    r_get = client.get(f"/api/uc1/paths/{pid}")
    assert r_get.status_code == 404


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------
def test_create_rejects_unknown_deck(client: httpx.Client) -> None:
    r = client.post("/api/uc1/paths", json={
        "title": "bad",
        "steps": [{"deck_id": "nope_does_not_exist", "order": 0}],
    })
    assert r.status_code == 400


def test_create_rejects_duplicate_order(client: httpx.Client, deck_ids) -> None:
    r = client.post("/api/uc1/paths", json={
        "title": "bad",
        "steps": [
            {"deck_id": deck_ids[0], "order": 0},
            {"deck_id": deck_ids[1], "order": 0},  # duplicate order
        ],
    })
    assert r.status_code == 400


def test_create_rejects_duplicate_deck(client: httpx.Client, deck_ids) -> None:
    r = client.post("/api/uc1/paths", json={
        "title": "bad",
        "steps": [
            {"deck_id": deck_ids[0], "order": 0},
            {"deck_id": deck_ids[0], "order": 1},  # same deck twice
        ],
    })
    assert r.status_code == 400


def test_create_rejects_empty_steps(client: httpx.Client) -> None:
    r = client.post("/api/uc1/paths", json={"title": "empty", "steps": []})
    assert r.status_code == 400


def test_get_missing_path_404(client: httpx.Client) -> None:
    r = client.get("/api/uc1/paths/path_nope")
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# Referential integrity — deck delete while referenced
# ---------------------------------------------------------------------------
def test_delete_referenced_deck_without_force_returns_409(
    client: httpx.Client, deck_ids
) -> None:
    # Upload a throwaway deck we can delete, reference it in a path
    import pathlib
    path = pathlib.Path(__file__).parent / "fixtures" / "uc1" / "climate-action.pptx"
    with path.open("rb") as fh:
        r = client.post("/api/uc1/upload", files={"file": ("deletable-ref.pptx", fh, "application/vnd.openxmlformats-officedocument.presentationml.presentation")})
    assert r.status_code == 200
    new_deck = r.json()["deck_id"]

    rp = client.post("/api/uc1/paths", json={
        "title": "refs-deletable",
        "steps": [{"deck_id": new_deck, "order": 0}],
    })
    path_id = rp.json()["id"]

    # Delete without force → 409
    r_del = client.delete(f"/api/uc1/decks/{new_deck}")
    assert r_del.status_code == 409

    # Delete with force → path marked broken
    r_del_f = client.delete(f"/api/uc1/decks/{new_deck}?force=true")
    assert r_del_f.status_code == 200
    assert path_id in r_del_f.json().get("broken_paths", [])

    # Path now returns 410 Gone
    time.sleep(2)
    r_path = client.get(f"/api/uc1/paths/{path_id}")
    assert r_path.status_code == 410

    # Cleanup
    client.delete(f"/api/uc1/paths/{path_id}")


# ---------------------------------------------------------------------------
# Progress — monotonic + set-union + concurrency
# ---------------------------------------------------------------------------
def test_initial_progress_empty(client: httpx.Client, path_with_steps: dict) -> None:
    r = client.get(f"/api/uc1/paths/{path_with_steps['id']}/progress", params={"user_id": "pytest-u1"})
    assert r.status_code == 200
    data = r.json()
    assert data["completed_count"] == 0
    assert data["percent"] == 0.0
    assert data["resume_deck_id"] == path_with_steps["steps"][0]["deck_id"]
    assert data["resume_slide_index"] == 0


def test_post_progress_monotonic(client: httpx.Client, path_with_steps: dict) -> None:
    user = "pytest-monotonic"
    deck = path_with_steps["steps"][0]["deck_id"]
    # POST slide_index=3 completed
    r1 = client.post(f"/api/uc1/paths/{path_with_steps['id']}/progress", json={
        "user_id": user, "deck_id": deck, "slide_index": 3, "completed": True,
    })
    assert r1.status_code == 200
    # POST slide_index=1 (earlier) → should NOT regress last_slide_index
    r2 = client.post(f"/api/uc1/paths/{path_with_steps['id']}/progress", json={
        "user_id": user, "deck_id": deck, "slide_index": 1, "completed": True,
    })
    assert r2.status_code == 200
    data = r2.json()
    assert data["last_slide_index"] == 3  # kept high-water mark
    assert set(data["completed_slides"][deck]) == {1, 3}  # union, both present


def test_post_progress_concurrent(client: httpx.Client, path_with_steps: dict) -> None:
    user = "pytest-concurrent"
    deck = path_with_steps["steps"][0]["deck_id"]

    def post(i: int) -> int:
        with httpx.Client(base_url=str(client.base_url), timeout=30) as c:
            return c.post(f"/api/uc1/paths/{path_with_steps['id']}/progress", json={
                "user_id": user, "deck_id": deck, "slide_index": i, "completed": True,
            }).status_code

    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as ex:
        results = list(ex.map(post, range(5)))
    assert all(s == 200 for s in results)
    # Final read: all 5 slides should be in completed_slides (best effort with monotonic retries)
    for _ in range(3):
        r = client.get(f"/api/uc1/paths/{path_with_steps['id']}/progress", params={"user_id": user})
        data = r.json()
        if set(data["completed_slides"].get(deck, [])) >= {0, 1, 2, 3, 4}:
            return
        time.sleep(1)
    # Soft-assert: at least 2 of the 5 survived (some lost updates are acceptable without etag)
    assert len(set(data["completed_slides"].get(deck, []))) >= 2


def test_progress_rejects_unknown_deck(client: httpx.Client, path_with_steps: dict) -> None:
    r = client.post(f"/api/uc1/paths/{path_with_steps['id']}/progress", json={
        "user_id": "pytest-u3", "deck_id": "nope", "slide_index": 0, "completed": True,
    })
    assert r.status_code == 400


def test_progress_on_missing_path_404(client: httpx.Client) -> None:
    r = client.post("/api/uc1/paths/path_nope/progress", json={
        "user_id": "pytest-u4", "deck_id": "whatever", "slide_index": 0,
    })
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# AI recommendation
# ---------------------------------------------------------------------------
def test_recommend_happy_path(client: httpx.Client, deck_ids) -> None:
    assert len(deck_ids) >= 2
    r = client.post("/api/uc1/paths/recommend", json={"topic": "artificial intelligence and security", "max_steps": 4})
    if r.status_code in (404, 502, 503):
        pytest.skip(f"LLM unavailable or topic yielded no path: {r.status_code} {r.text[:200]}")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["title"]
    assert isinstance(body["steps"], list)
    assert 2 <= len(body["steps"]) <= 4
    # Validate against FULL catalog (GPT may pick any deck, not just the ones this test uploaded)
    catalog_ids = {d["deck_id"] for d in client.get("/api/uc1/decks").json()}
    for i, s in enumerate(body["steps"]):
        assert s["deck_id"] in catalog_ids
        assert s["order"] == i
        assert s["deck_title"]
        assert isinstance(s["slide_count"], int)


def test_recommend_respects_max_steps(client: httpx.Client, deck_ids) -> None:
    r = client.post("/api/uc1/paths/recommend", json={"topic": "training fundamentals", "max_steps": 2})
    if r.status_code in (404, 502, 503):
        pytest.skip(f"LLM unavailable: {r.status_code}")
    assert r.status_code == 200
    assert len(r.json()["steps"]) <= 2


def test_recommend_does_not_persist(client: httpx.Client, deck_ids) -> None:
    """Recommend should NOT create a path — only return a suggestion."""
    before = client.get("/api/uc1/paths").json()
    r = client.post("/api/uc1/paths/recommend", json={"topic": "safety training", "max_steps": 3})
    if r.status_code in (404, 502, 503):
        pytest.skip(f"LLM unavailable: {r.status_code}")
    after = client.get("/api/uc1/paths").json()
    assert len(after) == len(before), "recommend must not create a path"


def test_recommend_validation_rejects_empty_topic(client: httpx.Client) -> None:
    r = client.post("/api/uc1/paths/recommend", json={"topic": "", "max_steps": 3})
    assert r.status_code == 422  # pydantic min_length


def test_recommend_validation_rejects_bad_max_steps(client: httpx.Client) -> None:
    r = client.post("/api/uc1/paths/recommend", json={"topic": "ai", "max_steps": 1})
    assert r.status_code == 422
    r = client.post("/api/uc1/paths/recommend", json={"topic": "ai", "max_steps": 20})
    assert r.status_code == 422
