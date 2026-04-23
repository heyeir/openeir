# Security & Privacy

## Modes

|  | Standalone | Eir |
|---|---|---|
| Search API calls | ✅ Brave, Tavily, etc. | ✅ Same |
| Crawl (fetch URLs) | ✅ | ✅ |
| Eir API calls | ❌ None | ✅ Opt-in |
| Reads USER.md | ❌ Never (default) | Only if personalization enabled |
| Personal data leaves machine | ❌ Never | Only generated content (see below) |

## Standalone Mode — What is sent

- **Search queries** to your configured search API (e.g. Brave, Tavily)
- **HTTP requests** to crawl source URLs for content
- **Nothing else.** No other external communication.

## Eir Mode — What is sent

| Data | Sent to Eir API | Notes |
|------|:---:|-------|
| Generated content (dot, l1, l2) | ✅ | LLM-generated summaries |
| l2.context, eir_take | ✅ | See personalization note below |
| Interest categories | ✅ | Topic slugs only (e.g. "ai-agents") |
| Source URLs + metadata | ✅ | For attribution |
| **USER.md content** | **❌ Never** | Used as local LLM prompt context only |
| **Raw conversation text** | **❌ Never** | Not accessed by pipeline |
| **System credentials** | **❌ Never** | |
| **File paths / machine identifiers** | **❌ Never** | |

### Personalization

Personalization is **off by default**. When enabled (`"personalization": {"enabled": true}` in `config/settings.json`), the pipeline reads your USER.md to provide context to the LLM during content generation. USER.md itself is never transmitted, but the LLM-generated `l2.context` and `eir_take` fields may reflect your professional context (e.g. "as an AI product builder...").

To disable: set `"personalization": {"enabled": false}` in `config/settings.json`, or simply don't enable it — it's off by default. When disabled, content is written for a general audience with no personal references.

### Interest Extraction

This skill includes a reference prompt (`references/interest-extraction-prompt.md`) that helps your agent learn your interests from conversations. It extracts only **de-identified topic labels and keywords** (e.g. "AI Agents", "autonomous vehicles") and saves them locally to `config/interests.json`. No raw conversation text or personal identifiers are stored.

If you already have a profile or interest skill installed, you can use that instead.

## Credential Storage

All credentials are stored locally in config files (gitignored). No secrets are hardcoded.

| File | Contains | Committed |
|------|----------|-----------|
| `config/eir.json` | Eir API key, user ID | ❌ gitignored |
| `config/settings.json` | Search API key, mode, preferences | ❌ gitignored |
| `config/interests.json` | Topic labels and keywords | ✅ no secrets |

## File Access

Pipeline scripts read/write only within the skill's `data/` and `config/` directories. The only external file access is optionally reading `USER.md` (when personalization is enabled).

## Reporting Vulnerabilities

Open an issue at [github.com/heyeir/openeir](https://github.com/heyeir/openeir/issues) or email security concerns directly.
