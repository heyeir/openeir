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

Curates personalized content based on your interests.

## Modes

**Eir mode** — Full AI-powered curation (requires heyeir.com account)
- Learns interests from conversations
- 5-step pipeline: plan → search → select → crawl → generate+post
- Content delivered to the Eir app

**Standalone mode** — Simple RSS aggregation
- Reads tech news from RSS feeds
- Delivers summaries directly in chat
- No account needed

---

## Eir Mode Pipeline

### Architecture (5 steps)

```
Step 0: plan         → GET /oc/curation → directives (topics + searchHints)
Step 1: search       → SearXNG (news-first → general fallback) → raw_results/
Step 2: select       → Cluster by topic → LLM judges candidates → candidates.json
Step 3: crawl        → Crawl candidate URLs via Crawl4AI → snippets/
Step 4+5: generate   → Agent LLM generates content → POST API → translate → POST
```

### Running the Pipeline

**Step 0 — Plan (fetch directives):**
```bash
python3 -m pipeline.search --dry-run   # preview queries
python3 -m pipeline.search             # runs plan + search
```
Search fetches directives from the API automatically before searching.

**Step 1 — Search:**
```bash
python3 -m pipeline.search
python3 -m pipeline.search --topic ai-agents   # single topic
```

**Step 2 — Select candidates:**
```bash
python3 -m pipeline.candidate_selector
python3 -m pipeline.candidate_selector --dry-run
```
Writes `candidate_prompt.txt` for agent LLM to evaluate.
Agent reads prompt, calls LLM, writes `candidates.json`.

**Step 3 — Crawl:**
```bash
python3 -m pipeline.crawl
python3 -m pipeline.crawl --dry-run
```
Only crawls URLs from accepted candidates. Includes freshness gate.

**Step 4+5 — Generate + POST (agent-driven):**
The agent imports `generate_and_post` module functions:
```python
from pipeline.generate_and_post import (
    get_candidates_for_generation,
    build_generation_prompt,
    post_to_api,
    build_translate_prompt,
    record_pushed,
    save_generated,
    save_posted,
    get_api_key,
)
```

Flow:
1. `get_candidates_for_generation()` → list of ready candidates with prompts
2. Agent calls LLM with `candidate["prompt"]` → gets JSON content
3. `post_to_api(content, api_key)` → returns (content_id, contentGroup)
4. `build_translate_prompt(content)` → agent calls LLM for EN translation
5. `post_to_api(en_content, api_key)` → POST translated version
6. `record_pushed(content, id, group)` → track what was posted

### Data Directories

All pipeline data lives in `<workspace>/data/v9/`:

| Directory | Contents |
|-----------|----------|
| `raw_results/` | Search results (by timestamp) |
| `candidates.json` | LLM-selected candidates |
| `snippets/` | Crawled article content |
| `generated/` | Generated content JSON |
| `posted/` | Successfully posted content |

Shared state (cross-run):
- `data/directives.json` — cached API directives
- `data/pushed_titles.json` — posting history
- `data/used_source_urls.json` — dedup URLs

### Content Quality Rules

See `references/content-spec.md` for full field constraints. Key rules:
- `dot.hook` ≤10 CJK chars, no hype words
- `dot.category`: `focus` | `attention` | `seed` | `whisper`
- `l1.bullets` 3-4 items, each ≤20 chars
- Never set any field to null — use `""` or `[]`
- Source attribution in `sources[]`, never inline
- Generate zh first, then translate to en (separate POST per language)

### Writer Prompt

The generation prompt is loaded from `references/writer-prompt-eir.md`.
Full field spec in `references/content-spec.md`.

---

## Agent Setup Flow

When user says "set up daily news" or similar, follow this step-by-step flow.

### Step 1: Check current setup

```bash
python3 scripts/setup.py --check
```

### Step 2: Choose mode

Ask user: **Standalone** (simple RSS) or **Eir** (full AI curation with heyeir.com account)?

### Step 3: Collect settings

| Setting | Default |
|---------|---------|
| Language | Auto-detect |
| Max items/day | 5 |
| Search (Tavily/Brave/SearXNG) | None (standalone) |

For Eir mode: connect account via `node scripts/connect.mjs <PAIRING_CODE>`

### Step 4: Initialize

```bash
python3 scripts/setup.py --init --settings '<json>'
```

### Step 5: Set schedule

```bash
openclaw cron add --name "eir-daily" --cron "0 8 * * *" --tz "Asia/Shanghai" \
  --session isolated --message "Run eir-daily-content-curator pipeline"
```

### Step 6: Test run

For standalone: `python3 scripts/standalone/curate.py`
For Eir: run pipeline steps 0-4+5

---

## Quick Reference

### Commands

| Task | Command |
|------|---------|
| Check setup | `python3 scripts/setup.py --check` |
| Search | `python3 -m pipeline.search` |
| Select candidates | `python3 -m pipeline.candidate_selector` |
| Crawl | `python3 -m pipeline.crawl` |
| Standalone curate | `python3 scripts/standalone/curate.py` |

### Infrastructure

| Service | URL | Purpose |
|---------|-----|---------|
| SearXNG | localhost:8888 | Meta-search engine |
| Crawl4AI | localhost:11235 | Web page crawler |
| Search Gateway | localhost:8899 | Search proxy (legacy) |

See `references/infrastructure-setup.md` for Docker setup.

### API Reference

See `references/eir-api.md` for endpoints and payload format.

### Version Check

Before running pipeline, verify schema compatibility:
1. Read `schema_version` from `GET /oc/curation`
2. Compare against `supported_schema_versions` in `config/settings.json`
3. Major version changes require skill update

### RSS Sources

Add feeds to `config/sources.json`:
```json
{
  "name": "Example Blog",
  "url": "https://example.com/feed.xml",
  "rating": "A",
  "lang": "en"
}
```
Ratings: S (4h), A (8h), B (24h).
