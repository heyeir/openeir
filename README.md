# OpenEir 📰

> AI reads the internet so you can think about what matters.

Learns your interests from conversations. Searches the web daily. Delivers a briefing that respects your time.

Built as an [OpenClaw](https://github.com/openclaw/openclaw) skill. Part of the [Eir](https://www.heyeir.com) ecosystem.

## Why

You're drowning in information. Twitter is chaos. Google News doesn't know you.

OpenEir learns what you actually care about from your conversations, searches for the latest on those topics, and delivers a daily briefing with only the things worth your attention.

No algorithms optimizing for clicks. No infinite scroll. Just signal.

## What you get

- 🎯 **Interest-aware** — Learns what you care about from conversations, not clicks or likes
- 🔍 **Smart curation** — Configurable search API with fallback chain, semantic dedup, relevance scoring
- 📋 **Daily Brief** — Opinionated summary of the day's most important signals
- 🌐 **Multilingual** — Read in your language, sourced from the world
- ✨ **[Eir](https://www.heyeir.com)** — Optional. Adds a visual reading canvas, interest visualization, Whisper journaling, and content history

## Quick Start

```bash
# Install via ClawHub
clawhub install eir-daily-content-curator

# Or clone directly
git clone https://github.com/heyeir/openeir.git
# Skill is at skills/eir-daily-content-curator/
```

Then tell your agent: *"Set up daily news for me"*

See [SKILL.md](skills/eir-daily-content-curator/SKILL.md) for full setup instructions.

## Configuration

### Standalone mode (default)

Edit `config/settings.json` with your search provider:
```json
{
  "mode": "standalone",
  "search": {
    "search_base_url": "https://api.your-provider.com/v3",
    "search_api_key": "YOUR_KEY"
  }
}
```

Recommended: Brave Search API, Tavily API, or any compatible search service.

### Eir mode (optional)

Connect to Eir for interest tracking, content delivery, and daily briefs:
```bash
node skills/eir-daily-content-curator/scripts/connect.mjs <PAIRING_CODE>
```

See [references/eir-setup.md](skills/eir-daily-content-curator/references/eir-setup.md) for full Eir setup.

## How it works

```
Interests → Search → Select + Crawl → Generate → Daily Brief
```

1. **Interest Extraction** — Scans conversations, builds topic list
2. **Search** — Queries search API for each topic (with SearXNG/Crawl4AI fallbacks)
3. **Select + Crawl** — LLM picks best candidates, fetches full content
4. **Generate** — Writes structured summaries from source material
5. **Daily Brief** — Compiles top items into an opinionated briefing

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
  --changelog "Initial release: dual-mode curation (standalone + Eir), 3-job pipeline, configurable search API, daily brief generation"

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
