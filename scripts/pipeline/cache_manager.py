#!/usr/bin/env python3
"""
Embedding-enhanced cache for eir-daily-curator pipeline.
Manages topic embeddings, article embeddings, and dual dedup.

All cache files live under DATA_DIR (~/.openclaw/workspace-content/data/).

Cache files and TTLs:
  context_cache.json   — Eir directives + topic embeddings      | overwritten each sync
  embed_cache.npz      — Article embedding vectors (numpy)       | 14 days
  embed_meta.json      — URL→index mapping + model metadata      | 14 days (matches npz)
  source_cache.json    — URL hash dedup (legacy L0)              | 14 days
  snippets/*.json      — Crawled article content                 | 7 days
  generated/*.json     — Generated content items (POST results)  | 30 days
  eir-feedback/*.md    — Daily run logs                          | 30 days
"""

import json
import hashlib
import glob
import os
import sys
from typing import Optional
from pathlib import Path
from datetime import datetime, timedelta

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from embed import EmbeddingService, MODEL_META

# All data lives here — single canonical location
DATA_DIR = Path.home() / ".openclaw" / "workspace-content" / "data"
FEEDBACK_DIR = Path.home() / ".openclaw" / "workspace-content" / "eir-feedback"

# Cache file paths
CONTEXT_CACHE = DATA_DIR / "context_cache.json"
EMBED_CACHE = DATA_DIR / "embed_cache.npz"
EMBED_META = DATA_DIR / "embed_meta.json"
SOURCE_CACHE = DATA_DIR / "source_cache.json"
SNIPPETS_DIR = DATA_DIR / "snippets"
GENERATED_DIR = DATA_DIR / "generated"

# TTL configuration (days)
TTL_ARTICLE_CACHE = 14   # embed_cache + embed_meta + source_cache
TTL_SNIPPETS = 7          # crawled article content
TTL_GENERATED = 30         # generated content items
TTL_FEEDBACK = 30          # daily run logs

# Thresholds
DEDUP_COSINE_THRESHOLD = 0.92  # Above = same story
RELEVANCE_HIGH = 0.7           # Strong topic match
RELEVANCE_MIN = 0.5            # Minimum to consider


class ContextCache:
    """Cache for Eir directives with topic embeddings.
    
    File: data/context_cache.json
    TTL: Overwritten each sync (no expiry needed)
    Content:
      - directives: list of Eir curation directives
      - topic_embeddings: {slug: [256-dim vector]} for each directive
      - user_embedding: [256-dim vector] from Eir user profile
      - model: embedding model metadata for verification
      - synced_at: ISO timestamp
    """

    def __init__(self, svc: EmbeddingService):
        self.svc = svc
        self.data = {}
        self._load()

    def _load(self):
        if CONTEXT_CACHE.exists():
            self.data = json.loads(CONTEXT_CACHE.read_text())

    def save(self):
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        CONTEXT_CACHE.write_text(json.dumps(self.data, indent=2, ensure_ascii=False))

    def update_from_eir(self, directives: list, user_embedding: Optional[list] = None):
        """Generate topic embeddings for directives and cache everything."""
        topic_texts = []
        for d in directives:
            text = f"{d.get('topic', '')}. {d.get('instruction', '')}"
            topic_texts.append(text)

        topic_embs = self.svc.embed_queries(topic_texts) if topic_texts else np.zeros((0, 256))

        topic_embeddings = {}
        for d, emb in zip(directives, topic_embs):
            topic_embeddings[d["slug"]] = emb.tolist()

        self.data = {
            "directives": directives,
            "topic_embeddings": topic_embeddings,
            "user_embedding": user_embedding,
            "model": MODEL_META,
            "synced_at": datetime.utcnow().isoformat() + "Z",
        }
        self.save()
        return len(directives)

    def get_topic_embedding(self, slug: str) -> "Optional[np.ndarray]":
        emb = self.data.get("topic_embeddings", {}).get(slug)
        return np.array(emb, dtype=np.float32) if emb else None

    def get_all_topic_embeddings(self) -> dict[str, np.ndarray]:
        result = {}
        for slug, emb in self.data.get("topic_embeddings", {}).items():
            result[slug] = np.array(emb, dtype=np.float32)
        return result


class ArticleEmbedCache:
    """Dual dedup cache: URL hash (L0) + embedding cosine (L1).
    
    Files:
      data/embed_cache.npz  — numpy array of article embeddings
      data/embed_meta.json  — article metadata + model info
      data/source_cache.json — URL→timestamp mapping (legacy compat)
    TTL: 14 days (pruned automatically)
    """

    def __init__(self, svc: EmbeddingService):
        self.svc = svc
        self.embeddings: np.ndarray = np.zeros((0, 256), dtype=np.float32)
        self.meta: dict = {"model": MODEL_META, "articles": []}
        self.url_hashes: set = set()
        self._load()

    def _load(self):
        if EMBED_CACHE.exists():
            data = np.load(EMBED_CACHE)
            self.embeddings = data["embeddings"]

        if EMBED_META.exists():
            self.meta = json.loads(EMBED_META.read_text())
            cached_model = self.meta.get("model", {}).get("name")
            if cached_model and cached_model != MODEL_META["name"]:
                print(f"⚠️  Model mismatch: cache={cached_model}, current={MODEL_META['name']}. Rebuilding.")
                self.embeddings = np.zeros((0, 256), dtype=np.float32)
                self.meta = {"model": MODEL_META, "articles": []}

        for art in self.meta.get("articles", []):
            self.url_hashes.add(art["url_hash"])

        if SOURCE_CACHE.exists():
            legacy = json.loads(SOURCE_CACHE.read_text())
            for url in legacy:
                self.url_hashes.add(self._hash_url(url))

    def save(self):
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(EMBED_CACHE, embeddings=self.embeddings)
        EMBED_META.write_text(json.dumps(self.meta, indent=2, ensure_ascii=False))

        # Sync to legacy source_cache.json
        legacy = {}
        if SOURCE_CACHE.exists():
            legacy = json.loads(SOURCE_CACHE.read_text())
        for art in self.meta.get("articles", []):
            if art["url"] not in legacy:
                legacy[art["url"]] = art.get("added_at", datetime.utcnow().isoformat() + "Z")
        SOURCE_CACHE.write_text(json.dumps(legacy, indent=2))

    @staticmethod
    def _hash_url(url: str) -> str:
        url = url.strip().rstrip("/").lower()
        url = url.replace("http://", "https://")
        url = url.split("?")[0].split("#")[0]
        return hashlib.md5(url.encode()).hexdigest()

    def check_duplicate(self, url: str, embedding: Optional["np.ndarray"] = None) -> tuple:
        """Dual dedup: L0 URL hash + L1 cosine similarity."""
        url_hash = self._hash_url(url)
        if url_hash in self.url_hashes:
            return True, "url_hash"

        if embedding is not None and len(self.embeddings) > 0:
            scores = self.svc.cosine_batch(embedding, self.embeddings)
            max_idx = int(np.argmax(scores))
            max_score = float(scores[max_idx])
            if max_score >= DEDUP_COSINE_THRESHOLD:
                similar_url = self.meta["articles"][max_idx]["url"] if max_idx < len(self.meta["articles"]) else "?"
                return True, f"semantic_{max_score:.3f}|{similar_url[:60]}"

        return False, ""

    def find_similar(self, embedding: np.ndarray, threshold: float = 0.7) -> list[tuple[int, float, dict]]:
        """Find articles similar to a given embedding."""
        if len(self.embeddings) == 0:
            return []
        scores = self.svc.cosine_batch(embedding, self.embeddings)
        results = []
        for i, s in enumerate(scores):
            if s >= threshold and i < len(self.meta["articles"]):
                results.append((i, float(s), self.meta["articles"][i]))
        return sorted(results, key=lambda x: x[1], reverse=True)

    def add_article(self, url: str, title: str, embedding: np.ndarray, extra: dict = None):
        """Add an article to the cache."""
        url_hash = self._hash_url(url)
        entry = {
            "url": url,
            "url_hash": url_hash,
            "title": title,
            "added_at": datetime.utcnow().isoformat() + "Z",
        }
        if extra:
            entry.update(extra)

        self.meta["articles"].append(entry)
        self.url_hashes.add(url_hash)

        embedding = embedding.reshape(1, -1).astype(np.float32)
        if len(self.embeddings) == 0:
            self.embeddings = embedding
        else:
            self.embeddings = np.vstack([self.embeddings, embedding])

    def prune(self, max_age_days: int = TTL_ARTICLE_CACHE):
        """Remove entries older than max_age_days."""
        cutoff = (datetime.utcnow() - timedelta(days=max_age_days)).isoformat() + "Z"
        keep = []
        keep_idx = []
        for i, art in enumerate(self.meta.get("articles", [])):
            if art.get("added_at", "9999") >= cutoff:
                keep.append(art)
                keep_idx.append(i)

        pruned = len(self.meta.get("articles", [])) - len(keep)
        if pruned > 0:
            self.meta["articles"] = keep
            if len(keep_idx) > 0 and len(self.embeddings) > 0:
                self.embeddings = self.embeddings[keep_idx]
            else:
                self.embeddings = np.zeros((0, 256), dtype=np.float32)
            self.url_hashes = {a["url_hash"] for a in keep}

        # Also prune legacy source_cache.json
        if SOURCE_CACHE.exists():
            legacy = json.loads(SOURCE_CACHE.read_text())
            pruned_legacy = {url: ts for url, ts in legacy.items() if (ts if isinstance(ts, str) else ts[0] if isinstance(ts, list) and ts else "") >= cutoff}
            legacy_pruned = len(legacy) - len(pruned_legacy)
            if legacy_pruned > 0:
                SOURCE_CACHE.write_text(json.dumps(pruned_legacy, indent=2))
                pruned += legacy_pruned

        return pruned

    def stats(self) -> dict:
        return {
            "total_articles": len(self.meta.get("articles", [])),
            "embedding_shape": list(self.embeddings.shape) if len(self.embeddings) > 0 else [0, 256],
            "url_hashes": len(self.url_hashes),
            "model": self.meta.get("model", {}).get("name", "unknown"),
        }


def prune_snippets(max_age_days: int = TTL_SNIPPETS) -> int:
    """Remove snippet files older than TTL."""
    if not SNIPPETS_DIR.exists():
        return 0
    cutoff = datetime.utcnow() - timedelta(days=max_age_days)
    pruned = 0
    for f in SNIPPETS_DIR.glob("*.json"):
        try:
            data = json.loads(f.read_text())
            fetched = data.get("fetched_at", "")
            if fetched and datetime.fromisoformat(fetched.replace("Z", "+00:00")).replace(tzinfo=None) < cutoff:
                f.unlink()
                pruned += 1
        except Exception:
            pass
    return pruned


def prune_generated(max_age_days: int = TTL_GENERATED) -> int:
    """Remove generated content dirs older than TTL."""
    if not GENERATED_DIR.exists():
        return 0
    cutoff = datetime.utcnow() - timedelta(days=max_age_days)
    pruned = 0
    for d in sorted(GENERATED_DIR.iterdir()):
        if d.is_dir():
            try:
                dir_date = datetime.strptime(d.name, "%Y-%m-%d")
                if dir_date < cutoff:
                    for f in d.glob("*"):
                        f.unlink()
                    d.rmdir()
                    pruned += 1
            except ValueError:
                pass
    return pruned


def prune_feedback(max_age_days: int = TTL_FEEDBACK) -> int:
    """Remove feedback logs older than TTL."""
    if not FEEDBACK_DIR.exists():
        return 0
    cutoff = datetime.utcnow() - timedelta(days=max_age_days)
    pruned = 0
    for f in FEEDBACK_DIR.glob("????-??-??.md"):
        try:
            file_date = datetime.strptime(f.stem, "%Y-%m-%d")
            if file_date < cutoff:
                f.unlink()
                pruned += 1
        except ValueError:
            pass
    return pruned


def prune_all() -> dict:
    """Run all prune operations. Called at start of eir-sync."""
    svc = EmbeddingService()
    cache = ArticleEmbedCache(svc)

    results = {
        "article_cache": cache.prune(TTL_ARTICLE_CACHE),
        "snippets": prune_snippets(TTL_SNIPPETS),
        "generated": prune_generated(TTL_GENERATED),
        "feedback": prune_feedback(TTL_FEEDBACK),
    }
    cache.save()
    return results


def rank_articles_for_topics(
    topic_embeddings: dict[str, np.ndarray],
    article_embeddings: list[tuple[dict, np.ndarray]],
) -> dict[str, list[tuple[dict, float]]]:
    """Rank articles by relevance to each topic."""
    if not article_embeddings:
        return {}

    articles, embs = zip(*article_embeddings)
    emb_matrix = np.vstack(embs)

    rankings = {}
    for slug, topic_emb in topic_embeddings.items():
        scores = EmbeddingService.cosine_batch(topic_emb, emb_matrix)
        ranked = [(articles[i], float(scores[i])) for i in range(len(articles)) if scores[i] >= RELEVANCE_MIN]
        ranked.sort(key=lambda x: x[1], reverse=True)
        rankings[slug] = ranked

    return rankings


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    if len(sys.argv) < 2:
        print("Usage: cache_manager.py <stats|prune|prune-all>")
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "stats":
        svc = EmbeddingService()
        cache = ArticleEmbedCache(svc)
        ctx = ContextCache(svc)

        print("=== Cache Statistics ===\n")
        print(f"Data dir: {DATA_DIR}\n")

        print("Article embed cache (TTL {0}d):".format(TTL_ARTICLE_CACHE))
        s = cache.stats()
        print(f"  Articles: {s['total_articles']}")
        print(f"  Embeddings: {s['embedding_shape']}")
        print(f"  URL hashes: {s['url_hashes']}")
        print(f"  Model: {s['model']}")

        print(f"\nContext cache (overwritten on sync):")
        print(f"  Directives: {len(ctx.data.get('directives', []))}")
        print(f"  Topic embeddings: {len(ctx.data.get('topic_embeddings', {}))}")
        print(f"  User embedding: {'yes' if ctx.data.get('user_embedding') else 'no'}")
        print(f"  Synced: {ctx.data.get('synced_at', 'never')}")

        snippet_count = len(list(SNIPPETS_DIR.glob("*.json"))) if SNIPPETS_DIR.exists() else 0
        print(f"\nSnippets (TTL {TTL_SNIPPETS}d): {snippet_count} files")

        gen_count = len(list(GENERATED_DIR.iterdir())) if GENERATED_DIR.exists() else 0
        print(f"Generated (TTL {TTL_GENERATED}d): {gen_count} dirs")

        fb_count = len(list(FEEDBACK_DIR.glob("*.md"))) if FEEDBACK_DIR.exists() else 0
        print(f"Feedback (TTL {TTL_FEEDBACK}d): {fb_count} files")

    elif cmd == "prune-all":
        results = prune_all()
        print("=== Prune Results ===")
        for k, v in results.items():
            print(f"  {k}: {v} removed")

    elif cmd == "prune":
        target = sys.argv[2] if len(sys.argv) > 2 else "all"
        days = int(sys.argv[3]) if len(sys.argv) > 3 else None
        if target == "all":
            results = prune_all()
            for k, v in results.items():
                print(f"  {k}: {v} removed")
        elif target == "articles":
            svc = EmbeddingService()
            cache = ArticleEmbedCache(svc)
            print(f"Pruned: {cache.prune(days or TTL_ARTICLE_CACHE)}")
            cache.save()
        elif target == "snippets":
            print(f"Pruned: {prune_snippets(days or TTL_SNIPPETS)}")
        elif target == "generated":
            print(f"Pruned: {prune_generated(days or TTL_GENERATED)}")
        elif target == "feedback":
            print(f"Pruned: {prune_feedback(days or TTL_FEEDBACK)}")

    else:
        print(f"Unknown: {cmd}")
        sys.exit(1)


if __name__ == "__main__":
    main()
