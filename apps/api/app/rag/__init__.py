"""Retrieval-Augmented Generation over official FTA source material.

Portable design:
- Embeddings default to an offline lexical embedder (no API key, deterministic) and
  upgrade to OpenAI embeddings when configured. Answer *generation* stays on the
  configured chat provider (e.g. Claude).
- Vectors are stored in the database and ranked by cosine similarity in Python, so
  the same code runs on SQLite (dev) and PostgreSQL (prod). A pgvector-backed
  ranker can replace the Python ranker at scale without changing callers.
"""
