---
name: eir-daily-content-curator
description: "Daily AI news curation — learns interests from conversations, searches the web, delivers structured summaries. Use when: 'set up daily news', 'curate content for me', 'what should I read today', 'personalized news briefing'."
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
- **Eir** — full AI-powered curation with [heyeir.com](https://heyeir.com) delivery

---

## Standalone Mode

A complete local curation pipeline. No Eir account required.

### Flow

```
1. Extract interests    → scan conversations, save to config/interests.json
2. Search              → Search API for each interest topic
3. Select + Crawl      → LLM picks best candidates, fetches full content
4. Generate            → LLM writes structured summaries to data/output/
5. Daily Brief         → Compile daily brief from generated items
```

### Quick Start

**Step 1: Configure search provider**

Edit `config/settings.json`:
```json
{
  "mode": "standalone",
  "search": {
    "search_base_url": "https://api.your-provider.com/v3",
    "search_api_key": "YOUR_KEY"
  }
}
```

Recommended providers: Brave Search API, Tavily API, or any compatible search service.

> **Optional fallback services:** If you run a local [SearXNG](https://docs.searxng.org/) or [Crawl4AI](https://github.com/unclecode/crawl4ai) instance, add `searxng_url` and `crawl4ai_url` to the search config. They serve as fallbacks when the primary search API returns no results. Neither is required.

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
cd scripts
python3 -m pipeline.search              # search for each topic
python3 -m pipeline.candidate_selector  # prepare topics for judgment
python3 -m pipeline.crawl               # fetch full content
python3 -m pipeline.pack_tasks          # bundle into task files

# Generate is agent-driven (LLM writes content from task files)
# Daily brief is agent-driven (LLM compiles daily summary)
```

**Step 4: Schedule daily cron**

```bash
# Material preparation + content generation
openclaw cron add --name "daily-curate" \
  --cron "0 8 * * *" --tz "Asia/Shanghai" \
  --session isolated \
  --message "Run eir-daily-content-curator: search → select → crawl → pack → generate content from task files."

# Daily brief (runs after generation completes)
openclaw cron add --name "daily-brief" \
  --cron "30 8 * * *" --tz "Asia/Shanghai" \
  --session isolated \
  --message "Check today's generated content in data/output/. Compile a daily brief: select 3-5 most important items, write a short opinionated summary for each, deliver to me."
```

### Output

Generated content is saved to `data/output/{date}/`:
```
data/output/2026-04-20/
  meta-layoffs-ai.json          # individual content items
  china-ai-regulation.json
  digest.md                     # compiled daily brief
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

### Daily Brief Format

The daily brief is a markdown file combining selected items:
```markdown
# Daily Brief — 2026-04-20

## 🔴 Focus
- **Meta cuts 8,000 jobs for AI pivot** — ...

## 🟡 Signals
- **China bans AI companions for minors** — ...

## 🌱 Seeds
- **New prompt engineering benchmark** — ...
```

---

## Eir Mode

Full AI-powered curation with delivery to the [Eir](https://heyeir.com) app.

### Flow

```
1. Fetch directives    → GET /oc/curation (topics + search hints from Eir API)
2. Search              → Search API + SearXNG for each directive
3. Select + Crawl      → LLM picks candidates, fetches full content
4. Pack tasks          → Bundle into self-contained task files
5. Generate + POST     → LLM writes content, POST to Eir Content API
6. Daily Brief + POST  → Compile brief, POST to Eir Brief API, deliver summary
```

### Setup

1. Connect Eir account: `node scripts/connect.mjs <PAIRING_CODE>`
2. Configure `config/eir.json` with API credentials
3. Set `"mode": "eir"` in `config/settings.json`

### Architecture (3-Job Pipeline)

```
Job A: material-prep
  search → select → crawl → pack
  Output: data/v9/tasks/{content_slug}.json

Job B: content-gen (runs after Job A)
  For each task → spawn subagent → generate → validate → POST
  Output: content posted to Eir Content API

Job C: daily-brief (runs after Job B completes)
  Check execution status → complete missing tasks →
  compile brief → POST to Eir Brief API → deliver summary
```

### Cron Setup

```bash
# Job A: Material preparation
openclaw cron add --name "eir-material-prep" \
  --cron "0 7 * * *" --tz "Asia/Shanghai" \
  --session isolated --agent content \
  --message "Run eir-daily-content-curator material prep: search → select → crawl → pack tasks."

# Job B: Content generation (35 min after Job A)
openclaw cron add --name "eir-content-gen" \
  --cron "35 7 * * *" --tz "Asia/Shanghai" \
  --session isolated --agent content \
  --message "Read task manifest, spawn subagents to generate content and POST to Eir API."

# Job C: Daily brief (10 min after Job B, after subagent timeout)
openclaw cron add --name "eir-daily-brief" \
  --cron "45 7 * * *" --tz "Asia/Shanghai" \
  --session isolated --agent content \
  --message "Check pipeline execution, complete missing tasks, compile daily brief, POST to brief API, send summary."
```

> **Timing:** Job C starts after Job B's subagent timeout (5 min) to ensure all content is generated before compiling the brief. Adjust gaps based on your typical task count.

### Content Quality Rules

- `dot.hook` ≤10 CJK chars / ≤6 EN words
- `dot.category`: `focus` | `attention` | `seed` | `whisper`
- `l1.bullets` 3-4 items, each ≤20 CJK chars
- `sources` must have at least 1 entry
- Never set any field to `null` — use `""` or `[]`

See `references/content-spec.md` for full field constraints.
See `references/writer-prompt-eir.md` for the generation prompt.

### Eir API Endpoints

| Endpoint | Purpose |
|----------|---------|
| `GET /oc/curation` | Fetch curation directives (topics + search hints) |
| `POST /oc/content` | Push generated content items |
| `POST /oc/brief` | Push daily brief |
| `POST /oc/curation/miss` | Report topics with no quality content found |

Base URL defaults to `https://api.heyeir.com/api`. Override with `EIR_API_URL` environment variable.

See `references/eir-api.md` for full API reference.

### Validation

```bash
cd scripts
python3 -m pipeline.validate_content           # check all generated files
python3 -m pipeline.validate_content --fix     # auto-fix common issues
```

---

## Shared Components

Both modes use these pipeline modules (in `scripts/pipeline/`):

| Module | Purpose |
|--------|---------|
| `search.py` | Search via configurable API (Brave/Tavily), SearXNG fallback |
| `crawl.py` | Fetch full content via Search Browse API, Crawl4AI fallback |
| `grounding.py` | Configurable search API client (baseURL + key) |
| `candidate_selector.py` | Group results by topic, prepare for LLM selection |
| `pack_tasks.py` | Bundle candidates into self-contained task files |
| `config.py` | Shared configuration and path resolution |
| `eir_config.py` | Workspace and API credential resolution |
| `date_extractor.py` | Extract publish dates from HTML |
| `validate_content.py` | Validate generated content against spec |

### Search Fallback Chain

```
Search API (primary) → SearXNG (fallback) → Crawl4AI/web_fetch (content)
```

All three are configurable in `config/settings.json`. Only the primary Search API is required; SearXNG and Crawl4AI are optional fallbacks.

### Configuration

`config/settings.json`:
```json
{
  "mode": "standalone",
  "search": {
    "search_base_url": "https://api.your-provider.com/v3",
    "search_api_key": "YOUR_KEY",
    "searxng_url": "http://localhost:8888",
    "crawl4ai_url": "http://localhost:11235"
  },
  "max_items_per_day": 8
}
```

| Field | Required | Description |
|-------|----------|-------------|
| `search_base_url` | Yes | Primary search API base URL |
| `search_api_key` | Yes | API key for the search provider |
| `searxng_url` | No | Local SearXNG instance (fallback search) |
| `crawl4ai_url` | No | Local Crawl4AI instance (fallback content fetch) |

### Dependencies

**Required:**
- Python 3.10+ (standard library only — no pip packages needed)
- Node.js 18+ (only for `connect.mjs` in Eir mode)

**Optional services (fallback):**
- [SearXNG](https://docs.searxng.org/) — local meta-search engine, used as search fallback
- [Crawl4AI](https://github.com/unclecode/crawl4ai) — local web crawler, used as content fetch fallback

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
| Setup workspace | `python3 scripts/setup.py --init --settings '{...}'` |
| Check setup | `python3 scripts/setup.py --check` |
| Search | `python3 -m pipeline.search` |
| Search (single topic) | `python3 -m pipeline.search --topic ai-health` |
| Select candidates | `python3 -m pipeline.candidate_selector` |
| Crawl | `python3 -m pipeline.crawl` |
| Pack tasks | `python3 -m pipeline.pack_tasks` |
| Validate | `python3 -m pipeline.validate_content` |
| Connect Eir | `node scripts/connect.mjs <PAIRING_CODE>` |
