# Security

## Credential Storage

All credentials are stored locally in `config/eir.json` (gitignored). No secrets are hardcoded or read from environment variables.

| File | Contains | Committed |
|------|----------|-----------|
| `config/eir.json` | Eir API key, pairing token | ❌ gitignored |
| `config/settings.json` | Search API key, mode config | ❌ gitignored |
| `config/interests.json` | User interest topics | ✅ no secrets |

## Data Flow

### Standalone Mode (default)
- **Outbound**: Search queries to your configured search API (e.g. Brave, Tavily)
- **Outbound**: HTTP requests to crawl source URLs
- **No other external communication**

### Eir Mode (opt-in)
All standalone flows, plus:
- **Outbound**: Generated content summaries → `api.heyeir.com`
- **Outbound**: Interest signals → `api.heyeir.com`
- **Inbound**: Curation directives ← `api.heyeir.com`

### What is NOT sent externally
- Raw conversation transcripts
- System credentials or environment variables
- Local file paths or machine identifiers
- Any data without explicit mode configuration

## Permissions

This skill requires:
- **Network**: Outbound HTTPS to search API and source URLs
- **Filesystem**: Read/write within the skill's `data/` and `config/` directories
- No elevated permissions, no shell spawning, no access outside skill directory

## Reporting Vulnerabilities

Open an issue at [github.com/heyeir/openeir](https://github.com/heyeir/openeir/issues) or email security concerns directly.
