# Infrastructure Setup Guide

The content pipeline uses local services for search and crawling. All are **optional** — in standalone mode, the pipeline uses Tavily/Brave web APIs instead.

| Service | Purpose | Default Port |
|---------|---------|-------------|
| SearXNG | Meta-search aggregator | 8888 |
| Crawl4AI | Full-article extraction | 11235 |

---

## 1. SearXNG

[SearXNG](https://github.com/searxng/searxng) is a privacy-respecting meta-search engine that aggregates results from 70+ search engines.

### Why

- No API keys or rate limits
- Aggregates Google, Bing, DuckDuckGo, and more in one query
- Full control over which engines are enabled per category

### Install (Docker)

```bash
mkdir -p ~/searxng && cd ~/searxng

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

### Docs

- GitHub: https://github.com/searxng/searxng
- Docker guide: https://docs.searxng.org/admin/installation-docker.html

---

## 2. Crawl4AI

[Crawl4AI](https://github.com/unclecode/crawl4ai) is an open-source web crawler optimized for LLM-ready content extraction. Returns clean markdown from web pages.

### Why

- Extracts article text as clean markdown (strips nav, ads, boilerplate)
- Handles JavaScript-rendered pages
- REST API for easy integration

### Install (Docker)

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
curl -s http://localhost:11235/health
# Expected: {"status": "ok"}
```

### Docs

- GitHub: https://github.com/unclecode/crawl4ai
- API reference: https://docs.crawl4ai.com/

---

## Configuration

After setting up the services, update `config/settings.json`:

```json
{
  "mode": "eir",
  "search": {
    "providers": ["searxng"],
    "searxng_url": "http://localhost:8888",
    "crawl4ai_url": "http://localhost:11235"
  }
}
```

---

## Health Check

```bash
#!/bin/bash
echo "=== SearXNG ==="
curl -sf 'http://localhost:8888/search?q=test&format=json' > /dev/null && echo "✅ OK" || echo "❌ Down"

echo "=== Crawl4AI ==="
curl -sf 'http://localhost:11235/health' && echo "" || echo "❌ Down"
```
