# OpenEir 📰

> Your AI agent already knows what you care about. OpenEir turns that into a daily briefing.

No manual topic setup. No feed subscriptions. No algorithm gaming for clicks. Your agent reads the internet, picks what matters to *you*, and explains why.

Built as an [OpenClaw](https://github.com/openclaw/openclaw) skill. Part of the [Eir](https://www.heyeir.com) ecosystem.

## What it looks like

```markdown
# Daily Brief — Apr 22

🔥 Anthropic launches Claude 4.5 — Major leap in multimodal reasoning, first to support real-time video understanding.
   Why it matters: Content understanding expands from text to video. Curation pipelines need new input channels.

📡 EU AI Act enforcement rules finalized — High-risk systems must complete compliance audits within 6 months.
   Worth watching: Compliance path for open-source models remains unclear, could reshape the agent ecosystem.

🌱 Cursor ships Background Agents — Cloud-sandboxed agents that complete dev tasks asynchronously.
   Builder's lens: Agent-as-a-service is moving from chat to async tasks — aligned with where Eir is heading.
```

Each item is personalized to your interests, with context on *why it matters to you*.

## What you get

- 🎯 **Interest-aware** — Learns what you care about from conversations, not clicks or likes
- 🔍 **Smart curation** — Configurable search API with fallback chain, semantic dedup, relevance scoring
- 📋 **Daily Brief** — Opinionated summary of the day's most important signals
- 🔓 **Zero lock-in** — Works standalone with any search API. No account required.
- 🌐 **Multilingual** — Read in your language, sourced from the world
- ✨ **[Eir mode](https://www.heyeir.com)** — Optional but recommended. Adds a visual reading canvas, interest visualization, Whisper journaling, and content history
<img width="1607" height="963" alt="image" src="https://github.com/user-attachments/assets/55ad726e-0b24-4bab-ab85-68a479263090" />


## Quick Start

```bash
# Install via ClawHub
clawhub install eir-daily-content-curator
```

Then tell your agent:

> *"Set up daily news for me"*

The agent will walk you through configuration — which search provider to use, what topics you care about, and when to deliver your briefing. That's it.

### Manual setup

If you prefer to configure everything yourself:

1. Initialize workspace:
```bash
python3 scripts/setup.py --init --settings '{
  "mode": "standalone",
  "search": {
    "search_base_url": "https://api.search.brave.com/res/v1",
    "search_api_key": "YOUR_KEY"
  }
}'
```
```

2. Create `config/interests.json` or let the agent extract interests from your conversations.

3. Run the pipeline or set up a daily cron.

See [SKILL.md](skills/eir-daily-content-curator/SKILL.md) for full setup instructions.

**Search providers:** [Brave Search API](https://brave.com/search/api/), [Tavily](https://tavily.com/), or any compatible service.

**Want richer results?** If you don't have a search API key, or want broader coverage, install [SearXNG](https://github.com/searxng/searxng) and/or [Crawl4AI](https://github.com/unclecode/crawl4ai) locally. They work as fallback or primary search/crawl providers.

## Eir mode (optional)

Connect to [Eir](https://www.heyeir.com) for interest tracking, a visual reading canvas, and content delivery:

```bash
node skills/eir-daily-content-curator/scripts/connect.mjs <PAIRING_CODE>
```

See [references/eir-setup.md](skills/eir-daily-content-curator/references/eir-setup.md) for full Eir setup.

## How it works

```
Interests → Search → Select + Crawl → Generate → Daily Brief
```

1. **Interest Extraction** — Scans conversations, builds a topic list automatically
2. **Search** — Queries search API for each topic (with optional SearXNG fallback)
3. **Select + Crawl** — LLM picks the best candidates, fetches full content
4. **Generate** — Writes structured summaries from source material
5. **Daily Brief** — Compiles top items into an opinionated briefing personalized to you

## Security & Data Flow

This skill makes outbound network requests to:
- **Your search API** (Brave/Tavily) — search queries only
- **heyeir.com** (Eir mode only, opt-in) — generated summaries, not raw conversations

No data leaves your machine in standalone mode unless you configure a search provider. Credentials stored locally in `config/eir.json` (gitignored).

## Documentation

| File | Contents |
|------|----------|
| [SKILL.md](skills/eir-daily-content-curator/SKILL.md) | Agent setup & pipeline guide |
| [references/eir-setup.md](skills/eir-daily-content-curator/references/eir-setup.md) | Eir mode setup, cron, API endpoints |
| [references/eir-api.md](skills/eir-daily-content-curator/references/eir-api.md) | Full Eir API reference |
| [references/content-spec.md](skills/eir-daily-content-curator/references/content-spec.md) | Content field constraints |

## Versioning & Publishing

### Version Management

The skill follows [semantic versioning](https://semver.org/):
- **Major** (X.0.0) — Breaking changes to config format, API contract, or pipeline architecture
- **Minor** (0.X.0) — New features, new pipeline steps, new search providers
- **Patch** (0.0.X) — Bug fixes, prompt improvements, documentation updates

Version is tracked in `config/settings.json` → `skill_version` and specified at publish time.

### Publishing to ClawHub

```bash
# First publish
clawhub publish ./skills/eir-daily-content-curator \
  --slug eir-daily-content-curator \
  --name "Daily Content Curator" \
  --version 1.0.0 \
  --changelog "Initial release: dual-mode curation (standalone + Eir), configurable search API, daily brief generation"

# Subsequent updates
clawhub publish ./skills/eir-daily-content-curator \
  --slug eir-daily-content-curator \
  --name "Daily Content Curator" \
  --version 1.1.0 \
  --changelog "Description of changes"
```

### Pre-publish Checklist

- [ ] No hardcoded API keys or secrets in any file
- [ ] No absolute paths (`/Users/...`, `/home/...`)
- [ ] No vendor-specific references in user-facing text
- [ ] `config/settings.json` has empty/placeholder credentials
- [ ] `config/eir.json` is in `.gitignore`
- [ ] All `__pycache__/` excluded
- [ ] SKILL.md description includes relevant trigger phrases
- [ ] Version bumped in publish command

## Contributing

PRs welcome — especially search provider integrations, language support, and quality improvements.

## License

MIT
