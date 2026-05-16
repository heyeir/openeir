---
name: eir-picks
description: "Evaluate public content from Eir's shared pool, write personalized connections, and post recommendations. Use when: 'evaluate public picks', 'eir picks', 'content recommendations'."
metadata:
  openclaw:
    emoji: "🎯"
    requires:
      bins: ["python3"]
---

# Eir Picks

Fetches content from [Eir](https://www.heyeir.com)'s shared content pool that matches your interests, evaluates each piece, and posts back personalized recommendations.

## What This Does

```
Your Eir interests → API returns matching public content → Agent evaluates
→ Writes "connection" (why it matters to you) → Posts recommendation back
```

You see the results in your Eir feed with personalized context.

---

## Prerequisites

Before setting up this skill, complete these steps on [heyeir.com](https://www.heyeir.com):

1. **Create an account** at heyeir.com
2. **Follow topics** — browse and follow interests that matter to you (AI, health, design, etc.)
3. **Get a pairing code** — go to **Settings → Connections → OpenClaw** and copy the pairing code

> The pairing code looks like `XXXX-XXXX`. Give it to your agent to complete setup.

---

## Setup

Give your agent the pairing code. The agent will:

1. Run the connect script to exchange the code for an API key:
   ```bash
   python3 scripts/eir_picks.py connect XXXX-XXXX
   ```
   This creates `config/eir.json` automatically.

2. Verify the connection:
   ```bash
   python3 scripts/eir_picks.py fetch
   ```

3. Set up a daily cron job:
   ```bash
   openclaw cron add \
     --name "eir-picks" \
     --cron "0 8 * * *" \
     --tz "YOUR_TIMEZONE" \
     --session isolated \
     --message "Run the eir-picks skill." \
     --announce
   ```

That's it. The agent handles everything from here.

---

## Agent Workflow

When triggered (cron or manual), do these steps:

### 1. Fetch picks

```bash
python3 scripts/eir_picks.py fetch > /tmp/eir_picks.json
```

Output contains:
- `publicPicks` — content items to evaluate
- `recentEngagements` — user's recent reading behavior
- `directives` — user's interest topics

### 2. Evaluate and write overlays

For each pick, decide:

| Field | Required | Value |
|-------|----------|-------|
| `contentId` | Yes | Copy from `publicPicks[].contentId` |
| `recommend` | Yes | `true` to recommend, `false` to skip |
| `connection` | No | 1-3 sentence personal insight (see below) |

### 3. Post overlays

```bash
echo '[{"contentId":"abc_zh","recommend":true,"connection":"Your insight..."}]' | python3 scripts/eir_picks.py post -
```

---

## Writing Connections

A **connection** is a private note explaining why this content matters to *this specific user*. Only they see it.

**Rules:**
- Match the pick's `lang` (zh pick → zh connection, en pick → en connection)
- 1-3 sentences, ≤800 chars
- Be specific — reference the user's context, projects, or recent reading
- If you can't write something sharp, omit it (just set `recommend: true`)

✅ "This agent identity standard solves the exact auth problem in multi-agent orchestration — your agents can't prove identity to third-party services today."

❌ "Interesting article about AI agents."

---

## Engagement Signals

`recentEngagements` shows what the user interacted with:

| Signal | Meaning |
|--------|---------|
| `article_click` | Opened the article |
| `detail_bottom` | Read to the end |
| `like` / `bookmark` / `share` | Strong positive signal |
| `impression` | Saw but didn't engage — they may already know this |

Use these to calibrate: deeply engaged topics → generous recommendations. Impression-only → don't repeat the same angle.

---

## Script Reference

```bash
python3 scripts/eir_picks.py connect CODE    # Exchange pairing code for API key
python3 scripts/eir_picks.py fetch           # Fetch picks → stdout JSON
python3 scripts/eir_picks.py post FILE       # Post overlays from file
python3 scripts/eir_picks.py post -          # Post overlays from stdin
```

---

## Troubleshooting

| Issue | Fix |
|-------|-----|
| Empty `publicPicks` | Follow more topics on heyeir.com, or the pool may be empty for new users |
| 401 error | Pairing expired — get a new code from Settings → Connections |
| All `recommend: false` | Normal — nothing relevant enough today |
