---
name: eir-daily-content-curator
description: "Daily AI news curation — learns interests from conversations, searches RSS + web, delivers summaries. Use when: 'set up daily news', 'curate content for me', 'what should I read today', 'personalized news briefing'."
metadata:
  {
    "openclaw":
      {
        "emoji": "📰",
        "requires": { "bins": ["python3", "curl"] },
      },
  }
---

# Daily Content Curator

Curates personalized content based on your interests. Supports two modes:

- **Standalone** — works locally, no external account needed
- **Eir** — full AI-powered curation with heyeir.com delivery

---

## Standalone Mode

A complete local curation pipeline. No Eir account required.

### Flow

```
1. Extract interests    → scan conversations, save to config/interests.json
2. Search              → Grounding API + RSS for each interest topic
3. Select + Crawl      → LLM picks best candidates, fetches full content
4. Generate            → LLM writes structured summaries to data/output/
5. Digest              → Compile daily digest from generated items
```

### Quick Start

**Step 1: Configure search provider**

Edit `config/settings.json`:
```json
{
  "mode": "standalone",
  "search": {
    "grounding_base_url": "https://api.your-provider.com/v3",
    "grounding_api_key": "YOUR_KEY"
  }
}
```

Recommended providers: Brave Search API, Tavily API, or any compatible grounding service.

**Step 2: Set up interests**

Option A — Manual: create `config/interests.json`:
```json
{
  "topics": [
    {"label": "AI Agents", "keywords": ["autonomous agents", "tool use", "agent frameworks"]},
    {"label": "Prompt Engineering", "keywords": ["prompting", "chain-of-thought"]}
  ],
  "language": "en",
  "max_items_per_day": 8
}
```

Option B — Auto-extract from conversations (agent-driven):
```
Read references/interest-extraction-prompt.md, then scan recent conversations
and write discovered topics to config/interests.json
```

**Step 3: Run the pipeline**

```bash
# Full pipeline (agent-driven, recommended)
# Agent reads this SKILL.md, runs each step in sequence

# Or run individual steps:
python3 -m pipeline.search              # search for each topic
python3 -m pipeline.candidate_selector  # prepare topics for judgment
python3 -m pipeline.crawl               # fetch full content
python3 -m pipeline.pack_tasks          # bundle into task files

# Generate is agent-driven (LLM writes content from task files)
# Digest is agent-driven (LLM compiles daily summary)
```

**Step 4: Schedule daily cron**

```bash
openclaw cron add --name "daily-curate" \
  --cron "0 8 * * *" --tz "Asia/Shanghai" \
  --session isolated \
  --message "Run the standalone content curation pipeline from eir-daily-content-curator skill. Follow SKILL.md Standalone Mode steps: search → select → crawl → pack → generate → digest. Deliver the digest summary to me."
```

### Output

Generated content is saved to `data/output/{date}/`:
```
data/output/2026-04-20/
  meta-layoffs-ai.json          # individual content items
  china-ai-regulation.json
  digest.md                     # compiled daily digest
```

Each item follows this format:
```json
{
  "title": "...",
  "summary": "2-3 sentences",
  "body": "2-4 paragraphs with analysis",
  "sources": [{"name": "...", "url": "...", "published": "..."}],
  "topic": "AI Industry",
  "generated_at": "2026-04-20T08:30:00Z"
}
```

### Digest Format

The daily digest is a markdown file combining all items:
```markdown
# Daily Digest — 2026-04-20

## 🔴 Focus
- **Meta cuts 8,000 jobs for AI pivot** — ...

## 🟡 Interesting
- **China bans AI companions for minors** — ...

## 🌱 Seeds
- **New prompt engineering benchmark** — ...
```

---

## Eir Mode

Full AI-powered curation with delivery to the Eir app (heyeir.com).

### Flow

```
1. Fetch directives    → GET /oc/curation (topics + search hints from API)
2. Search              → Grounding API + SearXNG for each directive
3. Select + Crawl      → LLM picks candidates, fetches full content
4. Pack tasks          → Bundle into self-contained task files
5. Generate + POST     → LLM writes content, POST to Eir Content API
```

### Setup

1. Connect Eir account: `node scripts/connect.mjs <PAIRING_CODE>`
2. Configure `config/eir.json` with API credentials
3. Set `"mode": "eir"` in `config/settings.json`

### Architecture (2-Job Split)

```
Job A: eir-material-prep (07:00)
  search → select → crawl → pack
  Output: data/v9/tasks/{content_slug}.json

Job B: eir-content-gen (07:45)
  For each task → spawn subagent → generate → POST
  Output: content posted to Eir API
```

### Cron Setup

```bash
# Material preparation
openclaw cron add --name "eir-material-prep" \
  --cron "0 7 * * *" --tz "Asia/Shanghai" \
  --session isolated \
  --message "Run eir-daily-content-curator material prep: search → select → crawl → pack tasks."

# Content generation
openclaw cron add --name "eir-content-gen" \
  --cron "45 7 * * *" --tz "Asia/Shanghai" \
  --session isolated \
  --message "Run eir-daily-content-curator content generation: read task files, generate content, POST to API."
```

### Content Quality Rules

- `dot.hook` ≤10 CJK chars / ≤6 EN words
- `dot.category`: `focus` | `attention` | `seed` | `whisper`
- `l1.bullets` 3-4 items, each ≤20 CJK chars
- `sources` must have at least 1 entry
- Never set any field to `null` — use `""` or `[]`
- Only generate zh (no translation)

See `references/content-spec.md` for full field constraints.
See `references/writer-prompt-eir.md` for the generation prompt.

### Validation

```bash
python3 -m pipeline.validate_content           # check all generated files
python3 -m pipeline.validate_content --fix     # auto-fix common issues
```

---

## Shared Components

Both modes use these pipeline modules:

| Module | Purpose |
|--------|---------|
| `pipeline/search.py` | Search via Grounding API (Brave/Tavily), SearXNG fallback |
| `pipeline/crawl.py` | Fetch full content via Grounding Browse, Crawl4AI fallback |
| `pipeline/grounding.py` | Generic grounding API client (configurable baseURL + key) |
| `pipeline/candidate_selector.py` | Group results by topic, prepare for LLM selection |
| `pipeline/pack_tasks.py` | Bundle candidates into self-contained task files |
| `pipeline/config.py` | Shared configuration and path resolution |
| `pipeline/date_extractor.py` | Extract publish dates from HTML |

### Search Fallback Chain

```
Grounding API (primary) → SearXNG (fallback) → Crawl4AI/web_fetch (content)
```

### Configuration

`config/settings.json`:
```json
{
  "mode": "standalone",
  "search": {
    "grounding_base_url": "https://api.your-provider.com/v3",
    "grounding_api_key": "YOUR_KEY",
    "searxng_url": "http://localhost:8888",
    "crawl4ai_url": "http://localhost:11235"
  },
  "max_items_per_day": 8
}
```

- `grounding_base_url` + `grounding_api_key`: Primary search provider
- `searxng_url`: Optional local SearXNG instance (fallback)
- `crawl4ai_url`: Optional local Crawl4AI instance (fallback)

---

## Interest Management

### Standalone: Local Interest Extraction

The agent extracts interests from recent conversations and saves to `config/interests.json`. See `references/interest-extraction-prompt.md` for extraction rules.

```json
{
  "topics": [
    {"label": "AI Agents", "keywords": ["autonomous agents", "tool use"], "freshness": "7d"},
    {"label": "华为汽车", "keywords": ["鸿蒙智行", "问界"], "freshness": "3d"}
  ],
  "language": "zh",
  "max_items_per_day": 8
}
```

### Eir: API-Synced Interests

Interests are managed via the Eir API (`GET /oc/curation` returns directives with search hints). See `references/eir-interest-rules.md` for tier guidelines.

---

## RSS Sources

Both modes can supplement search with RSS feeds. Configure in `config/sources.json`:

```json
{
  "rss": [
    {"name": "Techmeme", "url": "https://www.techmeme.com/feed.xml", "rating": "S", "lang": "en"},
    {"name": "TechCrunch", "url": "https://techcrunch.com/feed/", "rating": "A", "lang": "en"}
  ]
}
```

Ratings: S (check every 4h), A (8h), B (24h).

---

## References

| File | Contents |
|------|----------|
| `references/content-spec.md` | Field types, limits, validation rules |
| `references/eir-api.md` | Eir API endpoints and payloads |
| `references/writer-prompt-eir.md` | Eir mode content generation prompt |
| `references/writer-prompt-standalone.md` | Standalone mode generation prompt |
| `references/eir-interest-rules.md` | Curation tier guidelines |
| `references/interest-extraction-prompt.md` | Interest extraction from conversations |

---

## Quick Reference

| Task | Command |
|------|---------|
| Search | `python3 -m pipeline.search` |
| Search (single topic) | `python3 -m pipeline.search --topic ai-health` |
| Select candidates | `python3 -m pipeline.candidate_selector` |
| Crawl | `python3 -m pipeline.crawl` |
| Pack tasks | `python3 -m pipeline.pack_tasks` |
| Validate | `python3 -m pipeline.validate_content` |
| Standalone curate (legacy) | `python3 scripts/standalone/curate.py` |
