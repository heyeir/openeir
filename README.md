# OpenEir 📰

> AI reads the internet so you can think about what matters.

Learns your interests from conversations. Searches 40+ curated sources daily. Delivers a briefing that respects your time.

Built as an [OpenClaw](https://github.com/openclaw/openclaw) skill. Part of the [Eir](https://www.heyeir.com) ecosystem.

## Why

You're drowning in information. RSS is dead. Twitter is chaos. Google News doesn't know you.

OpenEir watches curated sources — from Techmeme to arXiv to Hacker News — learns what you actually care about from your conversations, and delivers a daily briefing with only the things worth your attention.

No algorithms optimizing for clicks. No infinite scroll. Just signal.

## What you get

- 🎯 **Interest-aware** — Learns from your conversations, not your clicks
- 📡 **40+ sources** — RSS + web search (Tavily/Brave), S/A quality-rated
- 🔍 **Quality filtering** — Source ratings, dedup, relevance scoring
- 🌐 **Bilingual** — Multi-language translation support
- ✨ **[Eir integration](https://www.heyeir.com)** — Connect for a beautiful reading canvas, Whisper journaling (capture and share your sparks of insight), enhanced local search (SearXNG + Crawl4AI), and adaptive interest tracking — all while your data stays yours

## Quick Start

```bash
# Install as OpenClaw skill
openclaw skill install heyeir/openeir

# Or clone directly
git clone https://github.com/heyeir/openeir.git
# Skill is at openeir/skills/eir-daily-content-curator/
```

Then tell your agent: *"Set up daily news for me"*

## Configuration

### Standalone mode (default)

Set search API key(s):
```bash
export TAVILY_API_KEY="tvly-..."   # recommended
export BRAVE_API_KEY="BSA..."      # fallback
```

### Eir mode (optional)

Connect to an Eir instance for interest tracking and content delivery:
```bash
export EIR_API_URL="https://api.heyeir.com"  # or your own instance
node skills/eir-daily-content-curator/scripts/connect.mjs <PAIRING_CODE>
```

### All environment variables

| Variable | Required | Description |
|----------|----------|-------------|
| `EIR_API_URL` | For Eir mode | Eir API base URL |
| `EIR_API_KEY` | For Eir mode | API key from pairing |
| `EIR_CONFIG` | No | Custom config file path (default: `config/eir.json`) |
| `TAVILY_API_KEY` | No | Tavily search API key (recommended) |
| `BRAVE_API_KEY` | No | Brave search API key (fallback) |

## How it works

```
Interests → Daily Plan → RSS Crawl → Web Search → Curate → Generate → Deliver
```

1. **Interest Sync** — Extracts topics from your conversations and memory
2. **Daily Plan** — Decides which sources to check and what to search
3. **Harvest** — Crawls RSS feeds + runs targeted web searches
4. **Curate** — Scores, deduplicates, ranks by relevance to *your* interests
5. **Generate** — Writes concise summaries in your language
6. **Deliver** — Sends your daily briefing at your preferred time

## Documentation

- [SKILL.md](skills/eir-daily-content-curator/SKILL.md) — Agent behavior & setup guide
- [references/eir-api.md](skills/eir-daily-content-curator/references/eir-api.md) — Full API reference (Eir mode)
- [references/quality-criteria.md](skills/eir-daily-content-curator/references/quality-criteria.md) — Content quality rules
- [config/sources.json](skills/eir-daily-content-curator/config/sources.json) — Default RSS sources
- [config/settings.json](skills/eir-daily-content-curator/config/settings.json) — Pipeline settings

## Contributing

PRs welcome — especially new content sources, language support, and quality improvements. See [SKILL.md](skills/eir-daily-content-curator/SKILL.md) for architecture details.

## License

MIT
