#!/usr/bin/env python3
"""
L1 Title semantic dedup for eir-collect pipeline.

Maintains a local cache of pushed content titles + embeddings.
Before POST to Eir API, check if a new title is semantically
too similar to any previously pushed title.

Cache file: data/pushed_titles.json
Embedding vectors: data/pushed_titles.npz

Usage (CLI):
  # Check if a title is duplicate
  echo '{"title":"SXSW 2026 认知达尔文主义","slug":"sxsw-topic"}' | python3 scripts/title_dedup.py check

  # Record a pushed title
  echo '{"title":"SXSW 2026 认知达尔文主义","slug":"sxsw-topic","content_id":"ci_xxx"}' | python3 scripts/title_dedup.py record

  # Batch check multiple titles
  echo '[{"title":"t1","slug":"s1"},{"title":"t2","slug":"s2"}]' | python3 scripts/title_dedup.py batch-check

  # Stats
  python3 scripts/title_dedup.py stats

  # Rebuild from eir-feedback logs
  python3 scripts/title_dedup.py rebuild

Usage (Python):
  from title_dedup import TitleDedup
  td = TitleDedup()
  is_dup, best_match, score = td.check("New title here")
  td.record("New title here", slug="topic-slug", content_id="ci_xxx")
"""

import json
import sys
import os
from pathlib import Path
from datetime import datetime
from typing import Optional, Tuple, List

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from embed import EmbeddingService
from eir_config import DATA_DIR

TITLES_META = DATA_DIR / "pushed_titles.json"
TITLES_NPZ = DATA_DIR / "pushed_titles.npz"

# Threshold: titles with cosine >= this are considered duplicates
# 0.85 is conservative — catches near-identical titles in different languages
# 0.80 catches paraphrases ("SXSW 2026 认知达尔文主义" vs "Brian Solis 认知达尔文主义与AI")
DEDUP_THRESHOLD = 0.82


class TitleDedup:
    """Semantic dedup for pushed content titles."""

    def __init__(self, threshold: float = DEDUP_THRESHOLD):
        self.threshold = threshold
        self._svc = EmbeddingService()
        self._meta: list[dict] = []
        self._vectors: Optional[np.ndarray] = None
        self._load()

    def _load(self):
        """Load existing title cache."""
        if TITLES_META.exists():
            with open(TITLES_META) as f:
                self._meta = json.load(f)
        else:
            self._meta = []

        if TITLES_NPZ.exists():
            data = np.load(TITLES_NPZ)
            self._vectors = data["vectors"]
        else:
            self._vectors = None

        # Sanity check: meta and vectors must match
        n_meta = len(self._meta)
        n_vec = self._vectors.shape[0] if self._vectors is not None else 0
        if n_meta != n_vec:
            print(f"[title_dedup] WARNING: meta({n_meta}) != vectors({n_vec}), rebuilding vectors", file=sys.stderr)
            self._rebuild_vectors()

    def _rebuild_vectors(self):
        """Rebuild embedding vectors from meta titles."""
        if not self._meta:
            self._vectors = None
            return
        titles = [m["title"] for m in self._meta]
        self._vectors = self._svc.embed_passages(titles)
        self._save_vectors()

    def _save_meta(self):
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        with open(TITLES_META, "w") as f:
            json.dump(self._meta, f, ensure_ascii=False, indent=2)

    def _save_vectors(self):
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        if self._vectors is not None and self._vectors.shape[0] > 0:
            np.savez_compressed(TITLES_NPZ, vectors=self._vectors)
        elif TITLES_NPZ.exists():
            TITLES_NPZ.unlink()

    def check(self, title: str) -> Tuple[bool, Optional[dict], float]:
        """
        Check if title is semantically duplicate to any pushed title.

        Returns:
            (is_duplicate, best_match_meta, best_score)
            best_match_meta is None if no match found.
        """
        if not self._meta or self._vectors is None or self._vectors.shape[0] == 0:
            return False, None, 0.0

        query_vec = self._svc.embed_queries([title])  # (1, 256)
        scores = self._svc.cosine_batch(query_vec[0], self._vectors)  # (N,)

        best_idx = int(np.argmax(scores))
        best_score = float(scores[best_idx])
        best_meta = self._meta[best_idx]

        is_dup = best_score >= self.threshold
        return is_dup, best_meta, best_score

    def batch_check(self, titles: List[str]) -> List[Tuple[bool, Optional[dict], float]]:
        """Check multiple titles at once (more efficient)."""
        if not self._meta or self._vectors is None or self._vectors.shape[0] == 0:
            return [(False, None, 0.0)] * len(titles)

        query_vecs = self._svc.embed_queries(titles)  # (M, 256)
        # scores: (M, N) = query_vecs @ vectors.T
        scores_matrix = query_vecs @ self._vectors.T

        results = []
        for i in range(len(titles)):
            scores = scores_matrix[i]
            best_idx = int(np.argmax(scores))
            best_score = float(scores[best_idx])
            best_meta = self._meta[best_idx]
            is_dup = best_score >= self.threshold
            results.append((is_dup, best_meta, best_score))
        return results

    def record(self, title: str, slug: str = "", content_id: str = "", source_urls: Optional[List[str]] = None, lang: str = ""):
        """Record a successfully pushed title."""
        # Check if already recorded (by content_id or exact title)
        for m in self._meta:
            if content_id and m.get("content_id") == content_id:
                return  # Already recorded
            if m["title"] == title:
                return  # Exact duplicate

        entry = {
            "title": title,
            "slug": slug,
            "content_id": content_id,
            "source_urls": source_urls or [],
            "lang": lang,
            "pushed_at": datetime.utcnow().isoformat() + "Z",
        }

        # Embed and append
        vec = self._svc.embed_passages([title])  # (1, 256)

        self._meta.append(entry)
        if self._vectors is None or self._vectors.shape[0] == 0:
            self._vectors = vec
        else:
            self._vectors = np.vstack([self._vectors, vec])

        self._save_meta()
        self._save_vectors()

    def stats(self) -> dict:
        return {
            "total_titles": len(self._meta),
            "vector_shape": list(self._vectors.shape) if self._vectors is not None else None,
            "threshold": self.threshold,
            "meta_file": str(TITLES_META),
            "npz_file": str(TITLES_NPZ),
        }


def main():
    if len(sys.argv) < 2:
        print("Usage: title_dedup.py <check|record|batch-check|stats|rebuild>")
        sys.exit(1)

    cmd = sys.argv[1]
    td = TitleDedup()

    if cmd == "stats":
        print(json.dumps(td.stats(), indent=2, ensure_ascii=False))

    elif cmd == "check":
        data = json.loads(sys.stdin.read())
        title = data["title"]
        is_dup, match, score = td.check(title)
        result = {
            "title": title,
            "is_duplicate": is_dup,
            "best_score": round(score, 4),
            "best_match": match,
            "threshold": td.threshold,
        }
        print(json.dumps(result, indent=2, ensure_ascii=False))

    elif cmd == "batch-check":
        items = json.loads(sys.stdin.read())
        titles = [item["title"] for item in items]
        results = td.batch_check(titles)
        output = []
        for item, (is_dup, match, score) in zip(items, results):
            output.append({
                "title": item["title"],
                "slug": item.get("slug", ""),
                "is_duplicate": is_dup,
                "best_score": round(score, 4),
                "best_match_title": match["title"] if match else None,
                "threshold": td.threshold,
            })
        print(json.dumps(output, indent=2, ensure_ascii=False))

    elif cmd == "record":
        data = json.loads(sys.stdin.read())
        td.record(
            title=data["title"],
            slug=data.get("slug", ""),
            content_id=data.get("content_id", ""),
            source_urls=data.get("source_urls", []),
        )
        print(json.dumps({"status": "recorded", "total": len(td._meta)}))

    elif cmd == "rebuild":
        # Rebuild vectors from existing meta
        td._rebuild_vectors()
        td._save_meta()
        print(json.dumps({"status": "rebuilt", "total": len(td._meta)}))

    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)


if __name__ == "__main__":
    main()
