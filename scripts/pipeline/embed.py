#!/usr/bin/env python3
"""
Embedding service for eir-daily-curator pipeline.
Uses EmbeddingGemma-300M with Matryoshka truncation to 256d.

Model: google/embeddinggemma-300m (300M params, Gemma 3 derived)
Method: Matryoshka Representation Learning — encode at 768d, truncate to 256d, re-normalize
Why 256d: Best balance of speed/storage vs distinction. Spread 2.5-3.5x better than e5-small 384d.

Usage:
  from embed import EmbeddingService
  svc = EmbeddingService()
  vectors = svc.embed_passages(["text1", "text2"])  # (N, 256) normalized
  score = svc.cosine(vec_a, vec_b)
"""

import json
import sys
import os
from pathlib import Path
import numpy as np

# Model configuration
MODEL_NAME = "embeddinggemma-300m"
MODEL_HF_ID = "google/embeddinggemma-300m"
FULL_DIM = 768
MATRYOSHKA_DIM = 256  # Truncated dimension (MRL: 768 → 256)
EMBEDDING_DIM = MATRYOSHKA_DIM
MAX_TOKENS = 2048  # EmbeddingGemma supports up to 2048 tokens
BATCH_SIZE = 32

# Model metadata (stored with cached embeddings for verification)
MODEL_META = {
    "name": MODEL_NAME,
    "hf_id": MODEL_HF_ID,
    "full_dim": FULL_DIM,
    "matryoshka_dim": MATRYOSHKA_DIM,
    "dim": EMBEDDING_DIM,
    "max_tokens": MAX_TOKENS,
    "method": "Matryoshka Representation Learning — encode at 768d, truncate first 256 dims, L2 normalize",
    "params": "300M",
    "source": "Google DeepMind, derived from Gemma 3",
}


class EmbeddingService:
    """Embedding service using EmbeddingGemma-300M + Matryoshka truncation."""

    def __init__(self):
        self._model = None
        self.meta = MODEL_META.copy()

    def _load(self):
        if self._model is not None:
            return
        from sentence_transformers import SentenceTransformer
        self._model = SentenceTransformer(MODEL_HF_ID, device="cpu")

    def _embed_and_truncate(self, texts: list[str]) -> np.ndarray:
        """Encode texts at full 768d, truncate to 256d, normalize."""
        self._load()
        if not texts:
            return np.zeros((0, EMBEDDING_DIM), dtype=np.float32)

        # Encode at full dimension (no normalization yet)
        full_embs = self._model.encode(texts, normalize_embeddings=False, batch_size=BATCH_SIZE)

        # Matryoshka truncation: take first MATRYOSHKA_DIM dimensions
        truncated = full_embs[:, :MATRYOSHKA_DIM].copy()

        # L2 normalize after truncation
        norms = np.linalg.norm(truncated, axis=1, keepdims=True)
        truncated = truncated / np.maximum(norms, 1e-12)

        return truncated.astype(np.float32)

    def embed_passages(self, texts: list[str]) -> np.ndarray:
        """Embed content for indexing."""
        return self._embed_and_truncate(texts)

    def embed_queries(self, texts: list[str]) -> np.ndarray:
        """Embed queries for retrieval. Same as passages for this model."""
        return self._embed_and_truncate(texts)

    @staticmethod
    def cosine(a: np.ndarray, b: np.ndarray) -> float:
        """Cosine similarity between two vectors."""
        a = a.flatten()
        b = b.flatten()
        return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-12))

    @staticmethod
    def cosine_batch(query: np.ndarray, matrix: np.ndarray) -> np.ndarray:
        """Cosine similarity between a query vector and a matrix of vectors."""
        query = query.flatten()
        return matrix @ query  # Already normalized

    def get_meta(self) -> dict:
        """Return model metadata for cache verification."""
        return self.meta.copy()


def main():
    if len(sys.argv) < 2:
        print("Usage: embed.py <passages|queries|meta>")
        sys.exit(1)

    cmd = sys.argv[1]
    svc = EmbeddingService()

    if cmd == "meta":
        print(json.dumps(svc.get_meta(), indent=2))
    elif cmd in ("passages", "queries"):
        texts = json.loads(sys.stdin.read())
        fn = svc.embed_passages if cmd == "passages" else svc.embed_queries
        vectors = fn(texts)
        print(json.dumps(vectors.tolist()))
    elif cmd == "similarity":
        data = json.loads(sys.argv[2] if len(sys.argv) > 2 else sys.stdin.read())
        a = np.array(data["a"], dtype=np.float32)
        b = np.array(data["b"], dtype=np.float32)
        print(f"{svc.cosine(a, b):.6f}")
    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)


if __name__ == "__main__":
    main()
