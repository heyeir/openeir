# Infrastructure Setup Guide

The Eir content pipeline uses three local services for enhanced search, crawling, and semantic dedup. All are **optional** — in standalone mode the pipeline uses Tavily/Brave web APIs instead. For Eir mode (self-hosted), these services provide better coverage, speed, and privacy.

| Service | Purpose | Default URL | Required? |
|---------|---------|-------------|-----------|
| SearXNG | Meta-search aggregator | `http://localhost:8888` | Optional (replaces Tavily/Brave) |
| Crawl4AI | Full-article extraction | `http://localhost:11235` | Optional (improves content quality) |
| Embedding model | Semantic dedup & topic matching | Local Python | Recommended |

---

## 1. SearXNG

[SearXNG](https://github.com/searxng/searxng) is a privacy-respecting meta-search engine that aggregates results from 70+ search engines.

### Why

- No API keys or rate limits
- Aggregates Google, Bing, DuckDuckGo, Brave, and more in one query
- Full control over which engines are enabled per category (general, news, science, etc.)

### Install (Docker — recommended)

```bash
mkdir -p ~/searxng && cd ~/searxng

# Create docker-compose.yml
cat > docker-compose.yml << 'EOF'
services:
  searxng:
    image: searxng/searxng:latest
    container_name: searxng
    ports:
      - "8888:8080"
    volumes:
      - ./settings.yml:/etc/searxng/settings.yml:ro
    environment:
      - SEARXNG_BASE_URL=http://localhost:8888/
    restart: unless-stopped
EOF

docker compose up -d
```

### Minimal `settings.yml`

```yaml
use_default_settings: true

server:
  secret_key: "change-me-to-a-random-string"
  bind_address: "0.0.0.0"
  port: 8080

search:
  formats:
    - html
    - json    # Required — pipeline uses JSON API

engines:
  # Enable/disable engines as needed
  - name: google
    disabled: false
  - name: bing
    disabled: false
  - name: duckduckgo
    disabled: false
  - name: brave
    disabled: false
```

### Verify

```bash
curl -s 'http://localhost:8888/search?q=test&format=json' | python3 -c "
import sys, json
data = json.load(sys.stdin)
print(f'Results: {len(data.get(\"results\", []))}')
"
```

### Official docs

- GitHub: https://github.com/searxng/searxng
- Docker guide: https://docs.searxng.org/admin/installation-docker.html
- Settings reference: https://docs.searxng.org/admin/settings/index.html

---

## 2. Crawl4AI

[Crawl4AI](https://github.com/unclecode/crawl4ai) is an open-source web crawler optimized for LLM-ready content extraction. It returns clean markdown from web pages.

### Why

- Extracts article text as clean markdown (strips nav, ads, boilerplate)
- Handles JavaScript-rendered pages
- Built-in content filtering by word count and HTML tags
- REST API for easy integration

### Install (Docker — recommended)

```bash
docker run -d \
  --name crawl4ai \
  -p 11235:11235 \
  --restart unless-stopped \
  unclecode/crawl4ai:latest
```

Or with Docker Compose:

```yaml
services:
  crawl4ai:
    image: unclecode/crawl4ai:latest
    container_name: crawl4ai
    ports:
      - "11235:11235"
    restart: unless-stopped
```

### Verify

```bash
# Health check
curl -s http://localhost:11235/health
# Expected: {"status": "ok"}

# Test crawl
curl -s -X POST http://localhost:11235/crawl \
  -H 'Content-Type: application/json' \
  -d '{"urls": ["https://example.com"], "word_count_threshold": 50}' \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('results',[{}])[0].get('markdown','')[:200])"
```

### How the pipeline uses it

- `rss_crawler.py` — crawls full article text for RSS items
- `backfill_snippets.py` — retries articles with missing/thin content
- `search_harvest.py` — crawls top search results for each topic

All scripts call `POST /crawl` with:
```json
{
  "urls": ["https://..."],
  "word_count_threshold": 100,
  "excluded_tags": ["nav", "footer", "header", "aside"],
  "bypass_cache": true
}
```

### Official docs

- GitHub: https://github.com/unclecode/crawl4ai
- API reference: https://docs.crawl4ai.com/

---

## 3. Embedding Model

The pipeline uses [EmbeddingGemma-300M](https://huggingface.co/google/embeddinggemma-300m) for semantic dedup and topic matching. This is a 300M-parameter embedding model from Google DeepMind, derived from Gemma 3.

### Model details

| Property | Value |
|----------|-------|
| Model | `google/embeddinggemma-300m` |
| Parameters | 300M |
| Full dimension | 768 |
| Truncated dimension | **256** (Matryoshka) |
| Max tokens | 2048 |
| Method | Matryoshka Representation Learning — encode at 768d, truncate first 256 dims, L2 normalize |
| License | Apache 2.0 |

### Why this model

- **Small and fast**: 300M params runs well on CPU (no GPU required)
- **Matryoshka support**: Encode once at 768d, truncate to 256d for storage — best balance of quality vs. speed
- **Good multilingual coverage**: Handles both English and Chinese content
- **256d after truncation**: 2.5-3x better spread than e5-small at 384d, with 33% less storage

### Install dependencies

```bash
pip install sentence-transformers numpy
```

The model downloads automatically on first use (~600MB). To pre-download:

```bash
python3 -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('google/embeddinggemma-300m')"
```

### Verify

```bash
cd scripts/pipeline/
python3 embed.py meta
```

Expected output:
```json
{
  "name": "embeddinggemma-300m",
  "hf_id": "google/embeddinggemma-300m",
  "full_dim": 768,
  "matryoshka_dim": 256,
  "dim": 256,
  "max_tokens": 2048,
  "method": "Matryoshka Representation Learning — encode at 768d, truncate first 256 dims, L2 normalize",
  "params": "300M",
  "source": "Google DeepMind, derived from Gemma 3"
}
```

### How the pipeline uses it

- `rss_crawler.py` — embeds article titles + descriptions for topic matching
- `search_harvest.py` — embeds search results, matches against topic embeddings (cosine > 0.5)
- `title_dedup.py` — L1 semantic dedup (cosine ≥ 0.82 = duplicate)
- `cache_manager.py` — stores embeddings in `.npz` files alongside article cache

### Official docs

- Hugging Face: https://huggingface.co/google/embeddinggemma-300m
- sentence-transformers: https://www.sbert.net/

---

## 4. Search Gateway (optional wrapper)

The pipeline scripts call a Search Gateway at `localhost:8899` which wraps SearXNG with:
- Engine priority routing by category (general, news, science, etc.)
- Automatic fallback (e.g., Google → Brave → Bing)
- Unified JSON response format

This is a thin HTTP wrapper. A minimal implementation:

```python
#!/usr/bin/env python3
"""Minimal Search Gateway — routes queries to SearXNG with category-based engine selection."""

import json
import urllib.parse
import urllib.request
from http.server import HTTPServer, BaseHTTPRequestHandler

SEARXNG_URL = "http://localhost:8888/search"

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if not self.path.startswith("/search"):
            self.send_error(404)
            return

        params = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        query = params.get("q", [""])[0]
        category = params.get("category", ["general"])[0]
        limit = int(params.get("limit", ["10"])[0])

        # Forward to SearXNG
        sx_params = urllib.parse.urlencode({
            "q": query,
            "format": "json",
            "categories": category,
        })
        try:
            req = urllib.request.Request(f"{SEARXNG_URL}?{sx_params}")
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read())
            results = [
                {"url": r["url"], "title": r.get("title", ""), "snippet": r.get("content", "")}
                for r in data.get("results", [])[:limit]
            ]
        except Exception as e:
            results = []

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"results": results, "results_count": len(results)}).encode())

    def log_message(self, format, *args):
        pass  # Suppress request logs

if __name__ == "__main__":
    print("Search Gateway listening on :8899")
    HTTPServer(("0.0.0.0", 8899), Handler).serve_forever()
```

Run: `python3 search_gateway.py &`

### Verify

```bash
curl -s 'http://localhost:8899/search?q=test&category=general&limit=3' | python3 -m json.tool
```

---

## Configuration

After setting up the services, update `config/settings.json`:

```json
{
  "mode": "eir",
  "search": {
    "providers": ["searxng"],
    "searxng_url": "http://localhost:8888",
    "crawl4ai_url": "http://localhost:11235",
    "search_gateway_url": "http://localhost:8899"
  }
}
```

The pipeline scripts also accept environment variables:
- `SEARCH_GATEWAY` — Search Gateway URL (default: `http://localhost:8899`)
- `CRAWL4AI_URL` — Crawl4AI URL (default: `http://localhost:11235`)

---

## Health checks

Quick script to verify all services:

```bash
#!/bin/bash
echo "=== SearXNG ==="
curl -sf 'http://localhost:8888/search?q=test&format=json' > /dev/null && echo "✅ OK" || echo "❌ Down"

echo "=== Crawl4AI ==="
curl -sf 'http://localhost:11235/health' && echo "" || echo "❌ Down"

echo "=== Search Gateway ==="
curl -sf 'http://localhost:8899/search?q=test&limit=1' > /dev/null && echo "✅ OK" || echo "❌ Down"

echo "=== Embedding Model ==="
python3 -c "from sentence_transformers import SentenceTransformer; m=SentenceTransformer('google/embeddinggemma-300m'); print('✅ OK (%dd)' % m.get_sentence_embedding_dimension())" 2>/dev/null || echo "❌ Not installed"
```
