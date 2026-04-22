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
1. Configure          → Set up search API + interests (one-time)
2. Search             → Search API queries for each interest topic
3. Select + Crawl     → Agent picks best candidates, fetches full content
4. Generate           → Agent writes structured summaries from task files
5. Daily Brief        → Agent compiles brief from generated items
```

> Steps 1-3 are Python scripts you run directly. Steps 4-5 are **agent-driven** — you tell your OpenClaw agent to read the task files and generate content. The agent uses whatever LLM model is configured in your OpenClaw session (e.g. Claude, GPT-4, Gemini).

### Quick Start

**1. Initialize workspace** — creates `config/` directory and default settings:
```bash
python3 scripts/setup.py --init --settings '{
  "mode": "standalone",
  "language": "en",
  "search": {
    "search_base_url": "https://api.search.brave.com/res/v1",
    "search_api_key": "YOUR_BRAVE_API_KEY"
  }
}'
```

Search provider examples:
| Provider | `search_base_url` | Get API key |
|----------|-------------------|-------------|
| Brave Search | `https://api.search.brave.com/res/v1` | [brave.com/search/api](https://brave.com/search/api/) |
| Tavily | `https://api.tavily.com` | [tavily.com](https://tavily.com/) |

> **Want richer results?** Install [SearXNG](https://docs.searxng.org/) and/or [Crawl4AI](https://github.com/unclecode/crawl4ai) locally. Add `searxng_url` and `crawl4ai_url` to your search config — they work as fallback or primary search/crawl providers.

**2. Set up interests** — edit the generated `config/interests.json`:
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

Interests can also be auto-extracted — see `references/interest-extraction-prompt.md`.

**3. Run the search + crawl pipeline** (from the `scripts/` directory):
```bash
cd scripts
python3 -m pipeline.search              # Search for each topic
python3 -m pipeline.candidate_selector  # Group results for agent selection
python3 -m pipeline.crawl               # Fetch full content
python3 -m pipeline.pack_tasks          # Bundle into task files
```

> All `python3 -m pipeline.*` commands must be run from the `scripts/` directory.

**4. Generate content** (agent-driven):

After `pack_tasks`, task files are in `data/v9/tasks/`. Tell your OpenClaw agent:

```
Read the task files in data/v9/tasks/ and generate content for each one.
Use the writer prompt in references/writer-prompt-standalone.md.
Save output to data/output/{YYYY-MM-DD}/.
```

Or schedule the full pipeline as a cron job:
```bash
openclaw cron add --name "daily-curate" \
  --cron "0 8 * * *" --tz "Asia/Shanghai" \
  --session isolated \
  --message "Read SKILL.md for eir-daily-content-curator, then run the full standalone pipeline: search → select → crawl → pack → generate content from task files → compile daily brief."
```

### Output

Content saved to `data/output/{YYYY-MM-DD}/`. Daily brief compiles the top items:

```markdown
# Daily Brief — 2026-04-20

🔥 **Meta cuts 8,000 jobs for AI pivot** — ...
📡 **China bans AI companions for minors** — ...
🌱 **New prompt engineering benchmark** — ...
```

### Dependencies

**Required:** Python 3.10+ (standard library only — no `pip install` needed).

**Optional:** Node.js 18+ (only for Eir connect script). [SearXNG](https://docs.searxng.org/) (fallback search). [Crawl4AI](https://github.com/unclecode/crawl4ai) (fallback crawl).

---

## Eir Mode

Full curation with delivery to the [Eir](https://www.heyeir.com) app via a 3-job pipeline:

```
Job A: material-prep     → Search → Select → Crawl → Pack tasks
Job B: content-gen       → Spawn subagents → Generate → POST to Eir
Job C: daily-brief       → Check status → Fill gaps → Compile brief → POST + Deliver
```

### Setup

1. Get a pairing code from [heyeir.com](https://www.heyeir.com) → Settings → Connect OpenClaw
2. Run: `node scripts/connect.mjs <PAIRING_CODE>`
3. Set `"mode": "eir"` in `config/settings.json`

For full Eir setup, cron configuration, content rules, and API details, see `references/eir-setup.md`.

---

## Pipeline Modules

All in `scripts/pipeline/`:

| Module | Purpose |
|--------|---------|
| `search.py` | Search via configurable API, SearXNG fallback |
| `crawl.py` | Fetch content via Browse API, Crawl4AI fallback |
| `grounding.py` | Configurable search API client |
| `candidate_selector.py` | Group results, prepare for agent selection |
| `pack_tasks.py` | Bundle candidates into task files |
| `validate_content.py` | Validate generated content against spec |
| `config.py` | Shared configuration and path resolution |
| `eir_config.py` | Workspace and credential resolution |

### Search Fallback Chain

```
Search API (primary) → SearXNG (optional) → Crawl4AI/web_fetch (content)
```

---

## References

| File | Contents | Used by |
|------|----------|---------|
| `references/writer-prompt-eir.md` | Content generation rules (Eir mode) | Agent |
| `references/writer-prompt-standalone.md` | Content generation rules (standalone) | Agent |
| `references/content-spec.md` | Field types, limits, validation rules | Agent |
| `references/eir-setup.md` | Eir mode setup, cron, API endpoints | Agent / User |
| `references/eir-api.md` | Full Eir API reference | Agent |
| `references/eir-interest-rules.md` | Curation tier guidelines | Agent |
| `references/interest-extraction-prompt.md` | Interest extraction prompt | Agent |

> The `writer-prompt-*.md` files are **instructions for the agent** — the agent reads them to know how to generate content from task files. You don't need to read them unless customizing output format.

---

## Security & Data Flow

This skill makes outbound network requests to:

- **Your configured search API** (e.g. Brave, Tavily) — sends search queries based on your interest topics
- **heyeir.com API** (Eir mode only, opt-in) — sends generated content summaries and interest signals

What is **NOT** sent externally:
- Local files or conversation history
- Environment variables or system credentials
- Any data in standalone mode (unless you configure a search API)

Credentials are stored locally in `config/eir.json` (gitignored). See `SECURITY.md` for full details.

---

## Quick Reference

| Task | Command |
|------|---------|
| Initialize workspace | `python3 scripts/setup.py --init --settings '{...}'` |
| Check setup | `python3 scripts/setup.py --check` |
| Search | `cd scripts && python3 -m pipeline.search` |
| Select candidates | `cd scripts && python3 -m pipeline.candidate_selector` |
| Crawl | `cd scripts && python3 -m pipeline.crawl` |
| Pack tasks | `cd scripts && python3 -m pipeline.pack_tasks` |
| Validate | `cd scripts && python3 -m pipeline.validate_content` |
| Connect Eir | `node scripts/connect.mjs <PAIRING_CODE>` |
