---
name: eir-picks
description: "Public content pool picks — evaluate shared content for personal relevance, generate connection overlays, and post recommendations. Use when: 'evaluate public picks', 'picks overlay', 'content connection', 'public content recommendations', 'personalized picks'."
metadata:
  openclaw:
    emoji: "🎯"
    requires:
      bins: ["python3"]
      env:
        EIR_API_KEY: "Eir API bearer token"
        EIR_API_URL: "Eir API base URL (optional override)"
---

# Eir Picks — Public Content Pool Overlay

Evaluates content from Eir's shared public pool and generates personalized **connection overlays** — brief notes explaining why a piece of content matters to a specific user.

> **Prerequisite:** This skill requires an active Eir connection. See `eir-daily-content-curator` for setup and pairing instructions.

## Concept

Eir maintains a **public content pool** — articles curated by all users in the network. When content in the pool matches your interests, the Curation API returns it as `publicPicks`. This skill:

1. **Fetches** public picks from the Curation API (via cached directives)
2. **Evaluates** each pick against user interests and recent engagement
3. **Generates** a `connection` overlay — a 1-3 sentence personalized insight
4. **POSTs** overlays back to `/oc/picks` so the user sees them in-app

```
┌─────────────────────────────────────────────────────┐
│  Public Content Pool (shared across all users)       │
│  ┌───────┐ ┌───────┐ ┌───────┐ ┌───────┐           │
│  │ pick1 │ │ pick2 │ │ pick3 │ │ pick4 │  ...       │
│  └───┬───┘ └───┬───┘ └───┬───┘ └───┬───┘           │
└──────┼─────────┼─────────┼─────────┼───────────────┘
       │         │         │         │
       ▼         ▼         ▼         ▼
┌─────────────────────────────────────────────────────┐
│  Curation API: filter by user interests              │
│  → Returns publicPicks (matched subset)              │
└──────┬──────────────────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────────────────────┐
│  eir-picks: Agent evaluates + writes connection      │
│  → POST /oc/picks with overlay for each pick         │
└─────────────────────────────────────────────────────┘
```

## Data Flow

### Input: `publicPicks` from Curation API

Each pick contains:
```json
{
  "contentId": "abc123_zh",
  "contentGroup": "abc123",
  "channelId": "eir-express",
  "lang": "zh",
  "title": "Example Title",
  "summary": "2-3 sentence summary...",
  "bullets": [{ "text": "Key fact 1" }, { "text": "Key fact 2" }],
  "topicSlugs": ["ai-agents"],
  "sourceUrls": ["https://example.com/article"]
}
```

### Output: Overlay POST to `/oc/picks`

```json
{
  "picks": [
    {
      "contentId": "abc123_zh",
      "recommend": true,
      "connection": "Why this matters to you specifically — 1-3 sentences."
    }
  ]
}
```

## Pipeline Integration

This skill is typically invoked as part of `eir-daily-content-curator`'s Job B (content generation), but can also run standalone.

### Standalone Usage

```python
from pipeline.picks_overlay import (
    get_cached_curation,
    get_public_picks_context,
    get_engagement_context,
    post_overlays,
    save_overlay_result,
)

# 1. Load cached curation data
curation = get_cached_curation()
picks = curation["publicPicks"]
engagements = curation["recentEngagements"]

# 2. Agent evaluates picks (LLM-driven)
# ... generate overlays ...

# 3. POST overlays
result = post_overlays(overlays)

# 4. Save local stats for reporting
save_overlay_result(overlays, len(picks))
```

### Within the Daily Pipeline

The picks evaluation happens during Job B (`eir-content-gen`). The agent:

1. Reads cached `publicPicks` from `data/directives.json` (fetched during Job A)
2. Uses `get_engagement_context()` to understand what the user recently engaged with
3. Evaluates each pick and writes a `connection` (or skips if not relevant enough)
4. Calls `post_overlays()` to submit recommendations

## Writing Good Connections

A `connection` is a **private, personalized** note explaining why a public content item matters to this specific user. It appears only for the user who generated it.

### Rules

| Rule | Details |
|------|---------|
| Language | Must match the content's `lang` field |
| Length | 1-3 sentences, ≤800 characters |
| Tone | Direct, insightful — not generic |
| When to skip | If you can't write a sharp personal angle, set `recommend: false` |
| No filler | "This is relevant to your interest in X" is not a connection |

### Good vs Bad Examples

**Good:** "This mirrors the exact architecture decision you're facing with your curation pipeline — event-driven vs polling. The latency numbers here are production-validated."

**Bad:** "Interesting article about AI agents that you might find relevant."

**Good:** "The FIDO Alliance's agent identity standard could solve the auth problem you noted in multi-agent orchestration — your agents currently can't prove identity to third-party services."

**Bad:** "AI agent security is a hot topic right now."

## Engagement Context

The skill uses recent engagement signals to better evaluate picks:

| Signal | Meaning |
|--------|---------|
| `impression` | User saw the card (skimmed) |
| `article_click` | User opened the article |
| `detail_bottom` | User read to the end |
| `like` | Explicit positive signal |
| `bookmark` | User saved for later |
| `share` | User shared externally |

Deep engagement (click + read + like/bookmark/share) on a topic → increase connection quality for related picks. Impression-only on a topic → the user already saw it, don't repeat the same angle.

## API Reference

### POST /oc/picks

Submit pick overlays (recommendations + connections).

**Request:**
```json
{
  "picks": [
    {
      "contentId": "abc123_zh",
      "recommend": true,
      "connection": "Personalized insight in content's language..."
    },
    {
      "contentId": "def456_en",
      "recommend": false
    }
  ]
}
```

**Response:**
```json
{
  "upserted": 2,
  "rejected": 0
}
```

**Notes:**
- `contentId` is required (from `publicPicks[].contentId`)
- `recommend` is boolean — controls whether the pick surfaces prominently
- `connection` is optional — only include when you have a genuine personal angle
- Rate limit: standard Eir API limits apply (see `eir-daily-content-curator` for retry logic)

## Configuration

This skill shares configuration with `eir-daily-content-curator`:

- **API credentials:** `config/eir.json` or `EIR_API_KEY` + `EIR_API_URL` env vars
- **Workspace:** resolved via `EIR_WORKSPACE` or `config/settings.json`

See [`eir-daily-content-curator` SKILL.md](../eir-daily-content-curator/SKILL.md) for full config reference.

## Module Reference

### `pipeline.picks_overlay`

| Function | Purpose |
|----------|---------|
| `get_cached_curation()` | Load cached picks + engagements from directives file |
| `get_public_picks_context()` | Compact text summary for candidate dedup |
| `get_engagement_context()` | Compact text summary of recent user engagement |
| `post_overlays(overlays)` | POST overlays to `/oc/picks` |
| `save_engagement_insight(insight)` | Save daily engagement analysis (LLM-generated) |
| `load_recent_insights(days=7)` | Load past engagement insights |
| `get_recent_insights_context(days=3)` | Compact text of recent insights for agent context |
| `save_overlay_result(overlays, picks_count)` | Save results locally for brief reporting |
| `get_overlay_stats()` | Load overlay stats for daily brief |

## Curation Stats

The API returns `curationStats` showing how picks were filtered:

```json
{
  "publicPicks": {
    "snapshotGroups": 100,
    "returned": 8,
    "readFiltered": 5,
    "impressionFiltered": 0,
    "duplicateGroups": 0,
    "unmatchedFiltered": 87,
    "coveredTopics": 6,
    "visibleCoveredTopics": 8
  }
}
```

| Field | Meaning |
|-------|---------|
| `snapshotGroups` | Total content groups in the public pool |
| `returned` | Picks returned to this user |
| `readFiltered` | Filtered because user already read them |
| `impressionFiltered` | Filtered because user already saw the card |
| `unmatchedFiltered` | Filtered because they don't match user interests |
| `coveredTopics` | Number of user topics covered by returned picks |

## Troubleshooting

| Issue | Fix |
|-------|-----|
| Empty `publicPicks` | Check that interests are set up and active. The pool may be empty for new accounts. |
| `POST /oc/picks` returns 401 | API key expired — run `python3 scripts/connect.py <CODE>` to re-pair |
| `recommend: true` but no `connection` | Valid — means "show this pick" without personalized note |
| All picks `recommend: false` | Fine — means nothing in the pool is relevant enough today |
