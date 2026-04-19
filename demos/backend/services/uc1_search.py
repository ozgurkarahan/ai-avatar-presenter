"""UC1 Learning Hub — Azure AI Search service.

Indexes slides from multiple decks into a single AI Search index, enabling
cross-deck semantic search ("ask anything across all your training decks").

Index schema (uc1-decks):
- id: str (unique, "{deck_id}-{slide_index}")
- deck_id: str (filterable)
- deck_title: str
- slide_index: int
- slide_title: str
- content: str (title + body + notes, searchable)
- language: str (filterable)
- embedding: vector(1536)  — text-embedding-3-small
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Optional

import httpx
from azure.core.credentials import AzureKeyCredential
from azure.search.documents import SearchClient
from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents.indexes.models import (
    HnswAlgorithmConfiguration,
    SearchField,
    SearchFieldDataType,
    SearchIndex,
    SimpleField,
    SearchableField,
    VectorSearch,
    VectorSearchProfile,
)

log = logging.getLogger(__name__)

EMBEDDING_DIMS = 1536  # text-embedding-3-small


@dataclass
class DeckSlide:
    deck_id: str
    deck_title: str
    slide_index: int
    slide_title: str
    body: str
    notes: str
    language: str


@dataclass
class SearchHit:
    deck_id: str
    deck_title: str
    slide_index: int
    slide_title: str
    snippet: str
    score: float


class Uc1SearchService:
    """Wraps Azure AI Search for the UC1 multi-deck index."""

    def __init__(
        self,
        endpoint: str,
        api_key: str,
        index_name: str,
        openai_client,
        embedding_deployment: str,
    ) -> None:
        self.endpoint = endpoint.rstrip("/")
        self.index_name = index_name
        self._cred = AzureKeyCredential(api_key)
        self._openai = openai_client
        self._embedding_deployment = embedding_deployment
        self._index_client = SearchIndexClient(self.endpoint, self._cred)
        self._search_client = SearchClient(self.endpoint, index_name, self._cred)
        self._ensure_index()

    # ------------------------------------------------------------------
    def _ensure_index(self) -> None:
        try:
            self._index_client.get_index(self.index_name)
            log.info("UC1 search index '%s' already exists", self.index_name)
            return
        except Exception:
            pass
        log.info("Creating UC1 search index '%s'", self.index_name)
        fields = [
            SimpleField(name="id", type=SearchFieldDataType.String, key=True),
            SimpleField(name="deck_id", type=SearchFieldDataType.String, filterable=True, facetable=True),
            SearchableField(name="deck_title", type=SearchFieldDataType.String),
            SimpleField(name="slide_index", type=SearchFieldDataType.Int32),
            SearchableField(name="slide_title", type=SearchFieldDataType.String),
            SearchableField(name="content", type=SearchFieldDataType.String),
            SimpleField(name="language", type=SearchFieldDataType.String, filterable=True, facetable=True),
            SearchField(
                name="embedding",
                type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
                searchable=True,
                vector_search_dimensions=EMBEDDING_DIMS,
                vector_search_profile_name="hnsw-default",
            ),
        ]
        vector_search = VectorSearch(
            algorithms=[HnswAlgorithmConfiguration(name="hnsw-config")],
            profiles=[VectorSearchProfile(name="hnsw-default", algorithm_configuration_name="hnsw-config")],
        )
        index = SearchIndex(name=self.index_name, fields=fields, vector_search=vector_search)
        self._index_client.create_or_update_index(index)
        log.info("UC1 search index created")

    # ------------------------------------------------------------------
    def _embed(self, text: str) -> list[float]:
        text = (text or " ").strip() or " "
        resp = self._openai.embeddings.create(model=self._embedding_deployment, input=text)
        return resp.data[0].embedding

    # ------------------------------------------------------------------
    def index_deck(self, slides: list[DeckSlide]) -> int:
        """Index (or re-index) all slides of a deck. Returns count uploaded."""
        if not slides:
            return 0
        docs = []
        for s in slides:
            content = f"{s.slide_title}\n\n{s.body}\n\nSpeaker notes: {s.notes}".strip()
            try:
                emb = self._embed(content)
            except Exception as e:
                log.exception("embedding failed for %s slide %d: %s", s.deck_id, s.slide_index, e)
                continue
            docs.append(
                {
                    "id": f"{s.deck_id}-{s.slide_index}",
                    "deck_id": s.deck_id,
                    "deck_title": s.deck_title,
                    "slide_index": s.slide_index,
                    "slide_title": s.slide_title or f"Slide {s.slide_index + 1}",
                    "content": content,
                    "language": s.language or "en-US",
                    "embedding": emb,
                }
            )
        if not docs:
            return 0
        result = self._search_client.upload_documents(docs)
        succeeded = sum(1 for r in result if r.succeeded)
        log.info("UC1 indexed %d/%d docs for deck %s", succeeded, len(docs), slides[0].deck_id)
        return succeeded

    # ------------------------------------------------------------------
    def delete_deck(self, deck_id: str) -> int:
        """Delete every chunk belonging to a deck."""
        # Search every doc for the deck and delete by key
        results = self._search_client.search(
            search_text="*",
            filter=f"deck_id eq '{deck_id}'",
            select=["id"],
            top=1000,
        )
        ids = [{"id": r["id"]} for r in results]
        if not ids:
            return 0
        result = self._search_client.delete_documents(ids)
        succeeded = sum(1 for r in result if r.succeeded)
        log.info("UC1 deleted %d/%d docs for deck %s", succeeded, len(ids), deck_id)
        return succeeded

    # ------------------------------------------------------------------
    def search(self, query: str, top_k: int = 5, language: Optional[str] = None) -> list[SearchHit]:
        """Hybrid search: vector + keyword. Returns top_k hits."""
        if not query.strip():
            return []
        try:
            qvec = self._embed(query)
        except Exception:
            log.exception("query embedding failed")
            qvec = None

        # Build search args
        from azure.search.documents.models import VectorizedQuery

        kwargs: dict = {
            "search_text": query,
            "top": top_k,
            "select": ["id", "deck_id", "deck_title", "slide_index", "slide_title", "content"],
        }
        if qvec:
            kwargs["vector_queries"] = [VectorizedQuery(vector=qvec, k_nearest_neighbors=top_k, fields="embedding")]
        if language:
            kwargs["filter"] = f"language eq '{language}'"

        try:
            results = self._search_client.search(**kwargs)
        except Exception:
            log.exception("UC1 search failed")
            return []

        hits: list[SearchHit] = []
        for r in results:
            content = r.get("content") or ""
            snippet = content[:280] + ("…" if len(content) > 280 else "")
            hits.append(
                SearchHit(
                    deck_id=r["deck_id"],
                    deck_title=r["deck_title"],
                    slide_index=r["slide_index"],
                    slide_title=r["slide_title"],
                    snippet=snippet,
                    score=float(r.get("@search.score", 0.0)),
                )
            )
        return hits


# ---------------------------------------------------------------------------
# Singleton accessor
# ---------------------------------------------------------------------------
_INSTANCE: Optional[Uc1SearchService] = None


def get_uc1_search(cfg, openai_client) -> Optional[Uc1SearchService]:
    """Return a singleton Uc1SearchService, or None if Search is not configured."""
    global _INSTANCE
    if _INSTANCE is not None:
        return _INSTANCE
    if not cfg.search_endpoint or not cfg.search_key:
        log.warning("UC1 search disabled (AZURE_SEARCH_ENDPOINT/KEY not set)")
        return None
    try:
        _INSTANCE = Uc1SearchService(
            endpoint=cfg.search_endpoint,
            api_key=cfg.search_key,
            index_name=cfg.search_index,
            openai_client=openai_client,
            embedding_deployment=cfg.openai_embedding_deployment,
        )
        return _INSTANCE
    except Exception:
        log.exception("UC1 search init failed")
        return None
