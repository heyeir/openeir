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

### Architecture

```
plan    → fetch directives from API (topics + search hints)
search  → SearXNG (news-first, general fallback)
select  → cluster by topic, LLM judges candidates
crawl   → fetch full article text for selected candidates
generate → LLM writes content → POST to API → translate → POST
```

### Running the Pipeline

```bash
# Search (fetches directives automatically, then searches)
python3 -m pipeline.search
python3 -m pipeline.search --topic ai-agents   # single topic
python3 -m pipeline.search --dry-run            # preview queries

# Select candidates (clusters results, writes prompt for LLM)
python3 -m pipeline.candidate_selector
python3 -m pipeline.candidate_selector --dry-run

# Crawl (fetches full text for selected candidate URLs)
python3 -m pipeline.crawl
python3 -m pipeline.crawl --dry-run
```

**Generate + POST** is agent-driven. The agent calls `generate_and_post` module functions to:
1. Load candidates with crawled content
2. Generate content via LLM using the writer prompt
3. POST to Eir Content API
4. Translate and POST the translated version

### Content Quality

See `references/content-spec.md` for full field constraints. Key rules:
- `dot.hook` ≤10 CJK chars / ≤6 EN words
- `dot.category`: `focus` | `attention` | `seed` | `whisper`
- `l1.bullets` 3-4 items, each ≤20 CJK chars
- Never set any field to `null` — use `""` or `[]`
- Source attribution in `sources[]`, never inline in prose
- Generate zh first, then translate to en (separate POST per language)

### Writer Prompt

Loaded from `references/writer-prompt-eir.md`. Full field spec in `references/content-spec.md`.

---

## Setup

When user says "set up daily news" or similar:

### 1. Check current setup
```bash
python3 scripts/setup.py --check
```

### 2. Choose mode
Ask user: **Standalone** (simple RSS) or **Eir** (full AI curation, requires heyeir.com account)?

### 3. Collect settings

| Setting | Default |
|---------|---------|
| Language | Auto-detect |
| Max items/day | 5 |
| Search provider | Tavily or Brave (standalone), SearXNG (self-hosted) |

For Eir mode, connect account: `node scripts/connect.mjs <PAIRING_CODE>`

### 4. Initialize
```bash
python3 scripts/setup.py --init --settings '<json>'
```

### 5. Set schedule
```bash
openclaw cron add --name "eir-daily" --cron "0 8 * * *" --tz "Asia/Shanghai" \
  --session isolated --message "Run eir-daily-content-curator pipeline"
```

### 6. Test run
- Standalone: `python3 scripts/standalone/curate.py`
- Eir: run the pipeline steps above

---

## Quick Reference

| Task | Command |
|------|---------|
| Check setup | `python3 scripts/setup.py --check` |
| Search | `python3 -m pipeline.search` |
| Select candidates | `python3 -m pipeline.candidate_selector` |
| Crawl | `python3 -m pipeline.crawl` |
| Standalone curate | `python3 scripts/standalone/curate.py` |

### Infrastructure

Self-hosted search and crawl services are optional. See `references/infrastructure-setup.md` for Docker setup.

### References

| File | Contents |
|------|----------|
| `references/content-spec.md` | Field types, limits, validation rules |
| `references/eir-api.md` | API endpoints and payloads |
| `references/writer-prompt-eir.md` | Content generation prompt |
| `references/writer-prompt-standalone.md` | Standalone mode prompt |
| `references/eir-interest-rules.md` | Curation tier guidelines |
| `references/whisper-api.md` | Whisper extraction API |
| `references/whisper-writer-prompt.md` | Whisper generation prompt |
| `references/infrastructure-setup.md` | SearXNG + Crawl4AI Docker setup |

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
