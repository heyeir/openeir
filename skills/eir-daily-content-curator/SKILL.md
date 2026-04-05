---
name: eir-daily-content-curator
description: "Daily AI news curation — learns interests from conversations, searches RSS + web, delivers summaries. Use when: 'set up daily news', 'curate content for me', 'what should I read today', 'personalized news briefing'."
metadata:
  {
    "openclaw":
      {
        "emoji": "📰",
        "requires": { "bins": ["python3", "curl"] },
      },
  }
---

# Daily Content Curator

Curates personalized content based on your interests.

## Agent Setup Flow


When user says "set up daily news" or similar, follow this **step-by-step conversational flow**. **Ask before doing** — explain what you're about to do and wait for confirmation.

---

### Step 1: Check current setup

First, check if already configured:

```bash
python3 scripts/setup.py --check
```

If already set up, show the current configuration and ask what they want to change. Otherwise proceed to Step 2.

---

### Step 2: Explain and choose mode

**Ask user which mode they want:**

> "I can set up daily content curation in two modes:
> 
> **A. Standalone** — Simple RSS aggregation
> • Reads tech news from RSS feeds
> • Delivers summaries directly here
> • No account needed, works immediately
> 
> **B. Eir** — Full AI-powered curation (requires heyeir.com account)
> • Learns your interests from conversations
> • Personalized content with deep-dive analysis
> • Reads in the Eir app with beautiful formatting
> 
> Which would you prefer?"

**Wait for user response.** Do not proceed until they choose.

---

### Step 3: Set workspace location

**Tell user where data will be stored (no need to ask):**

> "Data will be stored in your workspace: `~/.openclaw/workspace/eir/`
> This includes config, cache, and generated content."

**Set it immediately:**

```bash
python3 scripts/setup.py --set-workspace ~/.openclaw/workspace/eir
```

---

### Step 4: Collect settings with user

**Guide user through each setting. Ask for every item:**

| Setting | How to ask | Default |
|---------|-----------|---------|
| **Language** | "Content language? Chinese (zh) or English (en)?" | Auto-detect from conversation |
| **Max items/day** | "How many items per day? Recommend 5-10" | 5 |
| **Search** | "Enable web search? Requires API key (Tavily/Brave) or local SearXNG" | None |
| **Infrastructure** | "Have you set up SearXNG + Crawl4AI? (local search & crawl services, optional)" | No |

**For Standalone mode, ask about search:**

> "Enable web search?
> • **Yes** — Need Tavily or Brave API key (more comprehensive)
> • **No** — RSS only (simpler, no API dependency)
> 
> Your choice?"

**If they choose search, ask for API key:**

> "Which search service?
> 1. Tavily (recommended, free tier sufficient) — https://tavily.com
> 2. Brave Search — https://brave.com/search/api/
> 
> Provide API key or configure later?"

**For Eir mode, ask about connection:**

> "Need to connect Eir account. Open Eir app → Settings → Connect OpenClaw to get pairing code.
> 
> Have a pairing code?"

**If yes, run connect:**

```bash
node scripts/connect.mjs <PAIRING_CODE>
```

**If no:**

> "Can skip for now. Run `node scripts/connect.mjs <CODE>` later to connect."

---

### Step 5: Initialize with collected settings

**After collecting all settings, confirm with user:**

> "Confirm configuration:
> • Mode: Standalone
> • Language: zh
> • Max items/day: 5
> • Search: Tavily (API key configured)
> • Workspace: ~/.openclaw/workspace/eir/
> 
> Confirm create?"

**Wait for confirmation, then run:**

```bash
python3 scripts/setup.py --init --settings '{"mode":"standalone","language":"zh","max_items_per_day":5,"search":{"providers":["tavily"],"tavily_api_key":"xxx"}}'
```

---

### Step 6: Propose cron schedule

**After setup completes, propose a schedule and ask:**

> "Setup complete! Now configure delivery schedule.
> 
> Recommend: 8:00 AM daily
> • Frequency: Once per day
> • Timezone: Asia/Shanghai
> 
> Does that work? Or what time would you prefer?"

**If user confirms:**

```bash
openclaw cron add --name "eir-daily" --cron "0 8 * * *" --tz "Asia/Shanghai" --message "Run eir-daily-content-curator skill"
```

**If user wants different time, ask:**

> "What time would you prefer? (e.g., 7am, 9:30am, 8pm evening)"

Convert to cron:
- "7am" → `0 7 * * *`
- "9:30am" → `30 9 * * *`
- "8pm" → `0 20 * * *`

**Always confirm before creating:**

> "Set for 9:30 AM daily. Confirm?"

---

### Step 7: Test run

**Say:**

> "Let me fetch today's preview so you can see what it looks like..."

**Run:**

```bash
python3 scripts/standalone/curate.py
```

**Present results:**

> "Today's preview:
> 
> • **Claude 4 Released** (Anthropic Blog)
>   200K context window, native tool use...
>   https://...
> 
> • **Agent Evaluation Checklist** (LangChain)
>   Practical agent eval checklist...
>   https://...
> 
> This format look good?"

**If yes:**

> "Done! You'll receive your first update tomorrow at [time].
> Say 'pause daily news' or 'change delivery time' anytime to adjust."

**If user wants changes:**

> "What would you like to adjust? Topics, sources, or delivery time?"

---

## Output Format

```
• **[Claude 4 Released](https://anthropic.com/...)** (Anthropic Blog)
  200K context window, native tool use.

• **[Agent Evaluation Checklist](https://blog.langchain.com/...)** (LangChain)
  Practical agent eval checklist.
```

---

## Example Conversation

### Scenario 1: First-time setup

```
User: "Set up daily news for me"

Agent: "I can set up daily content curation in two modes:

A. Standalone — Simple RSS aggregation, no account needed
B. Eir — AI-powered personalization, requires heyeir.com account

Which would you prefer?"

User: "A, simpler"

Agent: "Data will be stored in ~/.openclaw/workspace/eir/

Content language? Chinese or English?"

User: "Chinese"

Agent: "How many items per day? Recommend 5-10"

User: "5"

Agent: "Enable web search? Need API key, or RSS only?"

User: "No search for now"

Agent: "Confirm config:
• Mode: Standalone
• Language: zh
• Max items/day: 5
• Search: None

Confirm create?"

User: "Yes"

Agent: [runs setup.py --init]
"Setup complete! Delivery time recommend 8 AM, OK?"

User: "OK"

Agent: [creates cron job]
"Done! Let me fetch a preview..."

Agent: [runs curate.py]
"Today's preview:...
This format look good?"

User: "Looks good"

Agent: "Tomorrow 8 AM you'll receive first update. Say 'pause' or 'change time' anytime."
```

### Scenario 2: User wants to change time

```
User: "Move my news to 9am"

Agent: "Update from 8am to 9am. Confirm?"

User: "Yes"

Agent: [updates cron job]
"Updated. Daily news now at 9:00 AM."
```

### Scenario 3: User wants to pause

```
User: "Pause my daily news"

Agent: "Pause delivery, settings saved. Say 'resume' anytime to restart. Confirm?"

User: "Yes"

Agent: [disables cron job]
"Paused."
```

---

## Quick Reference (For Agent)

### Commands

| Task | Command |
|------|---------|  
| Check setup | `python3 scripts/setup.py --check` |
| Set workspace | `python3 scripts/setup.py --set-workspace <path>` |
| Init with settings | `python3 scripts/setup.py --init --settings '<json>'` |
| Show workspace | `python3 scripts/setup.py --show-workspace` |
| Test curation | `python3 scripts/standalone/curate.py` |
| Cache health | `python3 scripts/pipeline/cache_cleanup.py --stats` |
| Cache cleanup | `python3 scripts/pipeline/cache_cleanup.py` |
| Markdown clean | `python3 scripts/pipeline/markdown_cleaner.py` |
| Add cron | `openclaw cron add --name "eir-daily" --cron "0 8 * * *" --tz "Asia/Shanghai" --message "..."` |
| List cron | `openclaw cron list` |
| Disable cron | `openclaw cron edit <id> --enabled=false` |
| Extract whispers | Run via OpenClaw agent (see below) |

### RSS Sources — Relevance Matters

The pipeline pre-filters RSS articles against your topics before storing them. Articles that don't match any of your interests are discarded immediately — no embedding stored, no snippet crawled.

**This means your RSS sources should align with your interests.**

- ✅ **Good**: Sources that frequently cover your tracked topics (AI, design, etc.)
- ⚠️ **Review**: General news aggregators (HN, Lobsters) — high volume, low match rate (~5%). Consider lowering their tier.
- ❌ **Waste**: Sources with zero overlap (e.g., automotive news when you have no automotive topics). Remove or wait until you add matching interests.

**Check your source ROI:**
```bash
python3 scripts/pipeline/cache_cleanup.py --stats
```

This shows match rate per source. Sources with <10% match rate are candidates for removal or tier downgrade.

**Adding sources that match your interests:**
- Find RSS feeds for blogs, newsletters, or publications you follow
- Add them to `config/sources.json` under the `"rss"` key
- Set `rating` to S (4h), A (8h), or B (24h) based on update frequency

```json
{
  "name": "Your Favorite Blog",
  "url": "https://example.com/feed.xml",
  "rating": "A",
  "lang": "en"
}
```

### Cache Health & TTL

The pipeline manages content freshness automatically:

| Content type | TTL | Rationale |
|---|---|---|
| Unmatched articles | 48h | Give topic matching 2 cycles to check, then discard |
| Matched articles | 7d | Available for content generation |
| Published source URLs | 30d | Kept for dedup |
| Orphan snippets | Immediate | No parent article, safe to remove |

Cleanup runs daily at 03:00 via cron. Manual run: `python3 scripts/pipeline/cache_cleanup.py`

### Whisper Extraction

The `whisper_extract.py` script analyzes Eir conversations to find "Whisper moments" — genuine intellectual collisions worth preserving. It generates polished mini-essays (Whispers) that appear in the user's Eir feed.

**How it works:**
1. Fetches conversations marked as `whisperCandidate` from Eir API
2. Uses LLM to analyze and generate Whisper content (dot, L1, L2)
3. Posts generated Whisper back to Eir via `POST /api/oc/whispers`

**Running via OpenClaw agent:**

Since Whisper extraction requires LLM analysis, it must be run through OpenClaw's agent system (not standalone Python):

```
# Agent runs this skill, which uses OpenClaw's configured model
# to analyze conversations and generate Whispers
```

The skill automatically:
- Uses OpenClaw's configured LLM (no separate model config needed)
- Connects to Eir API using stored credentials
- Processes whisper candidates incrementally

**Manual run (for testing):**
```bash
cd ~/.openclaw/workspace/eir
python3 scripts/pipeline/whisper_extract.py --dry-run
```

**Note:** The `--dry-run` flag previews without posting. Remove to actually create Whispers.

### Cron Schedule Examples

| User says | Cron expression |
|-----------|-----------------|
| "8am" | `0 8 * * *` |
| "9:30am" | `30 9 * * *` |
| "8pm" | `0 20 * * *` |
| "twice daily" | `0 8,20 * * *` |