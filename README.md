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
- **Eir integration**: Optional connection to [heyeir.com](https://heyeir.com) for enhanced reading experience

## Documentation

- [SKILL.md](SKILL.md) — Agent behavior & setup guide
- [references/eir-api.md](references/eir-api.md) — Full API reference
- [references/quality-criteria.md](references/quality-criteria.md) — Content quality rules
- [config/sources.json](config/sources.json) — Default RSS sources

## Pipeline

```
Interest Sync → Daily Plan → RSS Crawl → Search Harvest → Content Curation → Generate & Post
```

See [SKILL.md](SKILL.md) for full pipeline architecture and cron setup.

## License

MIT
