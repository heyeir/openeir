---
name: eir-daily-content-curator
description: "Daily AI news curation — learns interests from your profile, searches the web, delivers structured summaries and daily briefs. Use when: 'set up daily news', 'curate content for me', 'what should I read today', 'personalized news briefing', 'daily digest', 'news summary', 'content pipeline', 'interest tracking', 'automated content curation'."
metadata:
  {
    "openclaw":
      {
        "emoji": "📰",
        "requires": { "bins": ["python3"] },
      },
  }
---

# Daily Content Curator

Curates personalized content based on your interests. Supports two modes:

- **Standalone** — works locally, no external account needed
- **Eir** — full AI-powered curation with [heyeir.com](https://www.heyeir.com) delivery

## Standalone Mode

### Flow

```
1. Extract interests    → Define topics in config/interests.json or via Eir API
2. Search              → Search API for each interest topic
3. Select + Crawl      → LLM picks best candidates, fetches full content
4. Generate            → LLM writes structured summaries
5. Daily Brief         → Compile brief from generated items
```

### Quick Start

**1. Configure search provider** — edit `config/settings.json`:
```json
{
  "mode": "standalone",
  "search": {
    "search_base_url": "YOUR_BASE_URL",
    "search_api_key": "YOUR_KEY"
  }
}
```

Recommended providers: Brave Search API, Tavily API, or any compatible search service.

> **Want richer results?** If you don't have a search API key, or want broader coverage, install [SearXNG](https://docs.searxng.org/) and/or [Crawl4AI](https://github.com/unclecode/crawl4ai) locally. Add `searxng_url` and `crawl4ai_url` to your search config — they work as fallback or primary search/crawl providers.

**2. Set up interests** — create `config/interests.json`:
```json
{
  "topics": [
    {"label": "AI Agents", "keywords": ["autonomous agents", "tool use"], "freshness": "7d"},
    {"label": "Prompt Engineering", "keywords": ["prompting", "chain-of-thought"]}
  ],
  "language": "en",
  "max_items_per_day": 8
}
```

Interests can also be auto-extracted from conversations — see `references/interest-extraction-prompt.md`.

**3. Run the pipeline** (from the `scripts/` directory):
```bash
cd scripts
python3 -m pipeline.search              # search for each topic
python3 -m pipeline.candidate_selector  # LLM picks candidates
python3 -m pipeline.crawl               # fetch full content
python3 -m pipeline.pack_tasks          # bundle into task files
# Generate + brief are agent-driven (LLM writes from task files)
```

> All `python3 -m pipeline.*` commands must be run from the `scripts/` directory.

**4. Schedule daily cron:**
```bash
openclaw cron add --name "daily-curate" \
  --cron "0 8 * * *" --tz "Asia/Shanghai" \
  --session isolated \
  --message "Run eir-daily-content-curator: search → select → crawl → pack → generate → daily brief."
```

### Output

Content saved to `data/output/{date}/`. Daily brief compiles the top 3-5 items:

```markdown
# Daily Brief — 2026-04-20

🔥 **Meta cuts 8,000 jobs for AI pivot** — ...
📡 **China bans AI companions for minors** — ...
🌱 **New prompt engineering benchmark** — ...
```

---

## Eir Mode

Full curation with delivery to the [Eir](https://www.heyeir.com) app via a 3-job pipeline:

```
Job A: material-prep     → Search → Select → Crawl → Pack tasks
Job B: content-gen       → Spawn subagents → Generate → POST to Eir
Job C: daily-brief       → Check status → Fill gaps → Compile brief → POST + Deliver
```

**Setup:** `node scripts/connect.mjs <PAIRING_CODE>`, then set `"mode": "eir"`.

For full Eir setup, cron configuration, content rules, and API details, see `references/eir-setup.md`.

---

## Pipeline Modules

All in `scripts/pipeline/`:

| Module | Purpose |
|--------|---------|
| `search.py` | Search via configurable API, SearXNG fallback |
| `crawl.py` | Fetch content via Browse API, Crawl4AI fallback |
| `grounding.py` | Configurable search API client |
| `candidate_selector.py` | Group results, prepare for LLM selection |
| `pack_tasks.py` | Bundle candidates into task files |
| `validate_content.py` | Validate generated content against spec |
| `config.py` | Shared configuration and path resolution |
| `eir_config.py` | Workspace and credential resolution |

### Search Fallback Chain

```
Search API (primary) → SearXNG (optional) → Crawl4AI/web_fetch (content)
```

### Dependencies

**Required:** Python 3.10+ (standard library only). Node.js 18+ for Eir connect script.

**Optional:** [SearXNG](https://docs.searxng.org/) (fallback search), [Crawl4AI](https://github.com/unclecode/crawl4ai) (fallback crawl).

---

## References

| File | Contents |
|------|----------|
| `references/eir-setup.md` | Eir mode setup, cron, API endpoints |
| `references/content-spec.md` | Field types, limits, validation rules |
| `references/eir-api.md` | Full Eir API reference |
| `references/writer-prompt-eir.md` | Eir content generation prompt |
| `references/writer-prompt-standalone.md` | Standalone generation prompt |
| `references/eir-interest-rules.md` | Curation tier guidelines |
| `references/interest-extraction-prompt.md` | Interest extraction from conversations |

---

## Security & Data Flow

This skill makes outbound network requests to:

- **Your configured search API** (e.g. Brave, Tavily) — sends search queries based on your interest topics
- **heyeir.com API** (Eir mode only, opt-in) — sends generated content summaries and interest signals

What is **NOT** sent externally:
- Local files or conversation history
- Environment variables or system credentials
- Any data in standalone mode (unless you configure a search API)

Credentials are stored locally in `config/eir.json` (gitignored). No data leaves your machine without explicit mode configuration.

---

## Quick Reference

| Task | Command |
|------|---------|
| Setup workspace | `python3 scripts/setup.py --init --settings '{...}'` |
| Check setup | `python3 scripts/setup.py --check` |
| Search | `python3 -m pipeline.search` |
| Select candidates | `python3 -m pipeline.candidate_selector` |
| Crawl | `python3 -m pipeline.crawl` |
| Pack tasks | `python3 -m pipeline.pack_tasks` |
| Validate | `python3 -m pipeline.validate_content` |
| Connect Eir | `node scripts/connect.mjs <PAIRING_CODE>` |
