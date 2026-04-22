# Eir Mode Setup Guide

## Prerequisites

1. An Eir account at [heyeir.com](https://heyeir.com)
2. Node.js 18+ (for the connect script)

## Connect

```bash
node scripts/connect.mjs <PAIRING_CODE>
```

Get a pairing code from Eir → Settings → Connect OpenClaw. This saves credentials to `config/eir.json`.

Then set `"mode": "eir"` in `config/settings.json`.

## 3-Job Pipeline Architecture

```
Job A: material-prep
  Search → Select → Crawl → Pack
  Output: data/v9/tasks/{content_slug}.json

Job B: content-gen (runs after Job A)
  For each task → Spawn subagent → Generate → Validate → POST
  Output: content posted to Eir Content API

Job C: daily-brief (runs after Job B completes)
  Check execution status → Complete missing tasks →
  Compile brief → POST to Eir Brief API → Deliver summary
```

## Cron Setup

```bash
# Job A: Material preparation
openclaw cron add --name "eir-material-prep" \
  --cron "0 7 * * *" --tz "Asia/Shanghai" \
  --session isolated --agent content \
  --message "Run eir-daily-content-curator material prep: search → select → crawl → pack tasks."

# Job B: Content generation (35 min after Job A)
openclaw cron add --name "eir-content-gen" \
  --cron "35 7 * * *" --tz "Asia/Shanghai" \
  --session isolated --agent content \
  --message "Read task manifest, spawn subagents to generate content and POST to Eir API."

# Job C: Daily brief (10 min after Job B, after subagent timeout)
openclaw cron add --name "eir-daily-brief" \
  --cron "45 7 * * *" --tz "Asia/Shanghai" \
  --session isolated --agent content \
  --message "Check pipeline execution, complete missing tasks, compile daily brief, POST to brief API, send summary."
```

**Timing:** Job C starts after Job B's subagent timeout (5 min) to ensure all content is generated. Adjust gaps based on your typical task count.

## Content Quality Rules

- `dot.hook` ≤10 CJK chars / ≤6 EN words
- `dot.category`: `focus` | `attention` | `seed`
- `l1.bullets` 3-4 items, each ≤20 CJK chars
- `sources` must have at least 1 entry
- Never set any field to `null` — use `""` or `[]`

See `content-spec.md` for full field constraints.
See `writer-prompt-eir.md` for the generation prompt.

## API Endpoints

| Endpoint | Purpose |
|----------|---------|
| `GET /oc/curation` | Fetch curation directives (topics + search hints) |
| `POST /oc/content` | Push generated content items |
| `POST /oc/brief` | Push daily brief |
| `POST /oc/curation/miss` | Report topics with no quality content found |

Base URL defaults to `https://api.heyeir.com/api`. Override with `EIR_API_URL` environment variable.

See `eir-api.md` for full API reference.

## Validation

```bash
cd scripts
python3 -m pipeline.validate_content           # check all generated files
python3 -m pipeline.validate_content --fix     # auto-fix common issues
```
