---
name: eir-picks
description: "Evaluate public content from Eir's shared pool, write personalized connections, and post recommendations. Use when: 'evaluate public picks', 'content connection', 'public pool recommendations', 'eir picks cron'."
metadata:
  openclaw:
    emoji: "🎯"
    requires:
      bins: ["python3"]
---

# Eir Picks — Public Content Pool Recommendations

Evaluate content from Eir's shared content pool and generate personalized **connections** — brief insights explaining why each piece matters to the user.

## How It Works

Eir maintains a public content pool curated by all users. The Curation API filters this pool against your interests and returns **public picks**. This skill evaluates those picks and posts back overlays (recommend/skip + optional connection text).

```
Public Pool → Curation API filters by interests → publicPicks
    → Agent evaluates each pick → writes connection
    → POST /oc/picks with overlays
```

## Setup

### 1. Get Eir Credentials

You need an Eir account. Visit [heyeir.com](https://www.heyeir.com) to sign up, then generate an API key from Settings → Connections → OpenClaw.

### 2. Configure

Create `config/eir.json` in the skill directory:

```json
{
  "apiUrl": "https://api.heyeir.com",
  "apiKey": "YOUR_API_KEY"
}
```

Or set environment variables: `EIR_API_URL` + `EIR_API_KEY`.

### 3. Test

```bash
python3 scripts/eir_picks.py fetch | python3 -c "
import sys, json
d = json.load(sys.stdin)
print(f'Picks: {len(d[\"publicPicks\"])}, Topics: {len(d[\"directives\"])}')
"
```

## Cron Job Setup

Set up a daily cron to automatically evaluate picks:

```bash
openclaw cron add \
  --name "eir-picks" \
  --cron "0 8 * * *" \
  --tz "Asia/Shanghai" \
  --session isolated \
  --message "Run the eir-picks skill: fetch public picks, evaluate each one, write connections, and POST overlays." \
  --announce
```

The agent will:
1. Run `python3 scripts/eir_picks.py fetch` to get today's picks
2. Evaluate each pick using the rules below
3. Build an overlays JSON array
4. Run `python3 scripts/eir_picks.py post -` to submit

## Agent Instructions

When this skill is triggered (via cron or manually), follow these steps:

### Step 1: Fetch picks

```bash
python3 scripts/eir_picks.py fetch > /tmp/eir_picks.json
```

Read the output. It contains:
- `publicPicks` — content items to evaluate
- `recentEngagements` — what the user recently engaged with (signals: impression, article_click, detail_bottom, like, bookmark, share)
- `directives` — user's interest topics and tiers

### Step 2: Evaluate each pick

For each item in `publicPicks`, decide:

| Field | Required | Description |
|-------|----------|-------------|
| `contentId` | Yes | From `publicPicks[].contentId` |
| `recommend` | Yes | `true` = surface prominently, `false` = skip |
| `connection` | No | 1-3 sentence personalized insight (see rules below) |

### Step 3: Write connections

A **connection** is a private, personalized note — only this user sees it.

**Rules:**
- Language must match the pick's `lang` field
- 1-3 sentences, ≤800 characters
- Must be specific and insightful — not generic
- Better to omit than write filler
- Use engagement context: if user deeply engaged a related topic, the connection can build on that

**Good examples:**
- "The agent identity standard here directly addresses the auth gap in multi-agent orchestration — your agents can't prove identity to third-party APIs today."
- "Ford's pivot to energy storage mirrors your thesis that legacy automakers will find value adjacent to EVs, not in EVs themselves."

**Bad examples:**
- "This article about AI agents might be relevant to your interests."
- "Interesting development in the AI space."

### Step 4: Post overlays

Write the overlays array and POST:

```bash
cat <<'EOF' | python3 scripts/eir_picks.py post -
[
  {"contentId": "abc123_zh", "recommend": true, "connection": "Your insight here..."},
  {"contentId": "def456_en", "recommend": false}
]
EOF
```

The API returns `{"upserted": N, "rejected": 0}`.

### Step 5: Report

Summarize what you did:
- How many picks evaluated
- How many recommended vs skipped
- Any notable engagement patterns observed

## Engagement Signals

Use `recentEngagements` to understand what the user cares about:

| Signal | Weight | Meaning |
|--------|--------|---------|
| `share` | Highest | User shared externally — strong signal |
| `bookmark` | High | Saved for later reference |
| `like` | High | Explicit positive |
| `detail_bottom` | Medium | Read the full article |
| `article_click` | Medium | Opened the article |
| `impression` | Low | Saw the card but didn't engage |

If the user deeply engaged (click + read + like/bookmark) a topic, be more generous recommending related picks with detailed connections. If they only got impressions on a topic, they may already know about it — avoid repeating the same angle.

## API Reference

### GET /oc/curation → `publicPicks`

Returned as part of the curation response. Each pick:

```json
{
  "contentId": "abc123_zh",
  "contentGroup": "abc123",
  "channelId": "eir-express",
  "lang": "zh",
  "title": "Article Title",
  "summary": "Brief summary...",
  "bullets": [{"text": "Key fact 1"}, {"text": "Key fact 2"}],
  "topicSlugs": ["ai-agents"],
  "sourceUrls": ["https://example.com/article"]
}
```

### POST /oc/picks

Submit pick overlays.

**Request:** `{"picks": [{"contentId": "...", "recommend": true, "connection": "..."}]}`

**Response:** `{"upserted": N, "rejected": 0}`

## Curation Stats

The API also returns filtering statistics:

| Field | Meaning |
|-------|---------|
| `snapshotGroups` | Total content groups in the public pool |
| `returned` | Picks returned for this user |
| `readFiltered` | Filtered because already read |
| `unmatchedFiltered` | Filtered because no interest match |
| `coveredTopics` | User topics covered by returned picks |

## Troubleshooting

| Issue | Fix |
|-------|-----|
| `fetch` returns empty picks | User interests may not match pool content. Check that interests are active. |
| `post` returns 401 | API key expired. Re-generate from Eir Settings. |
| All picks `recommend: false` | Normal — means nothing relevant enough today. |
| `connection` rejected | Check language matches `lang`, and length ≤800 chars. |
