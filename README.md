# OpenEir

Open-source AI content curation skill for [OpenClaw](https://github.com/openclaw/openclaw).

Curates personalized content based on your interests — learns from conversations, searches RSS + web, delivers summaries.

## Quick Start

```bash
# Install as OpenClaw skill
openclaw skill install heyeir/openeir

# Or clone directly
git clone https://github.com/heyeir/openeir.git ~/.openclaw/skills/eir-daily-content-curator
```

Then tell your agent: *"Set up daily news for me"*

## Features

- **Interest-aware**: Learns topics from your conversations
- **Multi-source**: RSS feeds + web search (Tavily/Brave)
- **Quality filtering**: Source ratings, dedup, relevance scoring
- **Bilingual**: Generate content in zh/en with translation support
- **Eir integration** (optional): Connect to [heyeir.com](https://heyeir.com) for enhanced reading experience with deep-dive analysis

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
node scripts/connect.mjs <PAIRING_CODE>       # saves API key to config/eir.json
```

### All environment variables

| Variable | Required | Description |
|----------|----------|-------------|
| `EIR_API_URL` | For Eir mode | Eir API base URL |
| `EIR_API_KEY` | For Eir mode | API key from pairing |
| `EIR_CONFIG` | No | Custom config file path (default: `config/eir.json`) |
| `TAVILY_API_KEY` | No | Tavily search API key (recommended) |
| `BRAVE_API_KEY` | No | Brave search API key (fallback) |

## Documentation

- [SKILL.md](SKILL.md) — Agent behavior & setup guide
- [references/eir-api.md](references/eir-api.md) — Full API reference (Eir mode)
- [references/quality-criteria.md](references/quality-criteria.md) — Content quality rules
- [config/sources.json](config/sources.json) — Default RSS sources
- [config/settings.json](config/settings.json) — Pipeline settings

## Pipeline

```
Interest Sync → Daily Plan → RSS Crawl → Search Harvest → Content Curation → Generate & Post
```

See [SKILL.md](SKILL.md) for full pipeline architecture and cron setup.

## License

MIT
