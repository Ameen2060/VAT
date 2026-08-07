"""Embedding providers.

`HashingEmbedder` is a dependency-free lexical embedder: it maps text into a fixed
dimensional bag-of-words vector via feature hashing, with sublinear term frequency
and L2 normalisation. Cosine similarity then approximates lexical overlap — good
enough to retrieve the right VAT provisions by keyword, and it works with no API key.

`OpenAIEmbedder` uses OpenAI's embedding models when `OPENAI_API_KEY` is set, giving
semantic (not just lexical) retrieval.
"""

from __future__ import annotations

import hashlib
import math
import re
from typing import Protocol

from ..core.config import get_settings

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


class Embedder(Protocol):
    name: str
    dim: int

    def embed(self, text: str) -> list[float]: ...


class HashingEmbedder:
    name = "hashing"

    def __init__(self, dim: int = 512) -> None:
        self.dim = dim

    def _index(self, token: str) -> int:
        h = hashlib.md5(token.encode()).digest()
        return int.from_bytes(h[:4], "little") % self.dim

    def embed(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        counts: dict[str, int] = {}
        for tok in _tokenize(text):
            counts[tok] = counts.get(tok, 0) + 1
        for tok, c in counts.items():
            vec[self._index(tok)] += 1.0 + math.log(c)  # sublinear tf
        norm = math.sqrt(sum(v * v for v in vec))
        if norm > 0:
            vec = [v / norm for v in vec]
        return vec


class OpenAIEmbedder:
    name = "openai"

    def __init__(self, api_key: str, model: str = "text-embedding-3-small") -> None:
        import openai  # lazy import

        self._client = openai.OpenAI(api_key=api_key)
        self._model = model
        self.dim = 1536

    def embed(self, text: str) -> list[float]:
        resp = self._client.embeddings.create(model=self._model, input=text[:8000])
        return list(resp.data[0].embedding)


def get_embedder() -> Embedder:
    s = get_settings()
    if s.openai_api_key:
        try:
            return OpenAIEmbedder(api_key=s.openai_api_key)
        except Exception:  # noqa: BLE001 — fall back to offline embedder
            return HashingEmbedder()
    return HashingEmbedder()


def cosine(a: list[float], b: list[float]) -> float:
    if len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)
