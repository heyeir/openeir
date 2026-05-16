---
name: eir-picks
description: "Evaluate public content from Eir's shared pool, write personalized connections, and post recommendations. Use when: 'evaluate public picks', 'eir picks', 'content recommendations'."
metadata:
  openclaw:
    emoji: "🎯"
---

# Eir Picks

Fetches content from [Eir](https://www.heyeir.com)'s shared content pool that matches your interests, evaluates each piece, and posts back personalized recommendations with context.

```
Your interests → API returns matching content → You evaluate
→ Write "connection" (why it matters to you) → Post back
→ Content appears in your feed with personal context
```

---

## Prerequisites

Complete these steps on [heyeir.com](https://www.heyeir.com) first:

1. **Create an account** at heyeir.com
2. **Follow topics** — browse and follow interests (AI, health, design, etc.)
3. **Get a pairing code** — go to **Settings → Connections → OpenClaw**, copy the code

Give the pairing code to your agent to complete setup.

---

## Setup

### 1. Connect

Exchange the pairing code for an API key:

```
POST https://api.heyeir.com/api/oc/connect
Content-Type: application/json

{"code": "USER_PAIRING_CODE"}
```

Response: `{"apiKey": "...", "userId": "..."}`

Save the API key securely (e.g. environment variable `EIR_API_KEY` or a local config file).

### 2. Verify

```
GET https://api.heyeir.com/api/oc/curation
Authorization: Bearer API_KEY
```

Should return JSON with `publicPicks` array. If picks are empty, the user needs to follow more topics on heyeir.com.

### 3. Set up cron

```bash
openclaw cron add \
  --name "eir-picks" \
  --cron "0 8 * * *" \
  --tz "USER_TIMEZONE" \
  --session isolated \
  --message "Run the eir-picks skill." \
  --announce
```

---

## Agent Workflow

When triggered, follow these steps:

### 1. Fetch picks

```
GET https://api.heyeir.com/api/oc/curation
Authorization: Bearer API_KEY
```

Response contains:
- **`publicPicks`** — content to evaluate (title, summary, bullets, lang, topicSlugs)
- **`recentEngagements`** — user's recent reading signals
- **`directives`** — user's interest topics and priority tiers

### 2. Evaluate each pick

For each item in `publicPicks`, decide:

| Field | Required | Description |
|-------|----------|-------------|
| `contentId` | Yes | From the pick's `contentId` field |
| `recommend` | Yes | `true` = show prominently, `false` = skip |
| `connection` | No | 1-3 sentence personal insight |

### 3. Post overlays

```
POST https://api.heyeir.com/api/oc/picks
Authorization: Bearer API_KEY
Content-Type: application/json

{
  "picks": [
    {"contentId": "abc123_zh", "recommend": true, "connection": "Why this matters to you..."},
    {"contentId": "def456_en", "recommend": false}
  ]
}
```

Response: `{"upserted": N, "rejected": 0}`

---

## Writing Connections

A **connection** is a private note explaining why content matters to *this specific user*.

**Rules:**
- Language must match the pick's `lang` field
- 1-3 sentences, ≤800 characters
- Be specific — reference user's context, projects, or recent reading
- If nothing sharp to say, omit it (just `recommend: true` is fine)

✅ "This agent identity standard solves the exact auth gap in multi-agent orchestration — agents can't prove identity to third-party services today."

❌ "Interesting article about AI agents."

---

## Engagement Signals

Use `recentEngagements` to understand what the user cares about:

| Signal | Meaning |
|--------|---------|
| `article_click` / `detail_bottom` | User read the article |
| `like` / `bookmark` / `share` | Strong positive signal |
| `impression` only | Saw but didn't engage — may already know this |

Deeply engaged topics → generous recommendations. Impression-only → don't repeat the same angle.

---

## Troubleshooting

| Issue | Fix |
|-------|-----|
| Empty `publicPicks` | User needs to follow more topics on heyeir.com |
| 401 error | API key expired — get new pairing code from Settings → Connections |
| All `recommend: false` | Normal — nothing relevant today |
