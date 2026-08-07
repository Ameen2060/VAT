"""Tests for the RAG knowledge base: embeddings, ingestion, retrieval, chat grounding."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app
from app.rag.embeddings import HashingEmbedder, cosine


def test_hashing_embedder_similarity():
    emb = HashingEmbedder()
    a = emb.embed("reverse charge on imported services and SaaS subscriptions")
    b = emb.embed("does reverse charge apply to imported software services")
    c = emb.embed("first supply of a residential building zero rated")
    assert cosine(a, a) > 0.99
    # The two reverse-charge sentences should be closer than an unrelated one.
    assert cosine(a, b) > cosine(a, c)


def test_seed_and_search_and_chat_grounding():
    with TestClient(app) as client:
        seeded = client.post("/api/knowledge/seed").json()
        assert seeded["total_documents"] >= 10

        # Search retrieves the reverse-charge provision for a relevant query.
        hits = client.get("/api/knowledge/search", params={"q": "imported SaaS reverse charge"}).json()
        assert len(hits) > 0
        assert any("48" in (h["source_ref"] or "") for h in hits)

        # Chat is grounded: citations returned, offline stub echoes retrieved context.
        res = client.post(
            "/api/chat",
            json={"messages": [{"role": "user", "content": "Does reverse charge apply to imported SaaS?"}]},
        ).json()
        assert res["grounded"] is True
        assert len(res["citations"]) > 0
        assert "reverse charge" in res["reply"].lower()


def test_seed_is_idempotent():
    with TestClient(app) as client:
        client.post("/api/knowledge/seed")
        second = client.post("/api/knowledge/seed").json()
        assert second["added"] == 0
