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

## Agent Behavior

### Step 1: Observe context (don't ask yet)

Before asking anything, check what you already know:

1. **Language**: User just spoke to you — use that language
2. **Interests**: 
   - Check MEMORY.md for recorded interests/preferences
   - Recall recent conversations — what topics came up?
   - Look at workspace files — what projects are they working on?
3. **Timezone**: Check system timezone or infer from conversation context

### Step 2: Propose based on what you know

If you found interests:
```
"Based on our previous conversations, you seem interested in AI Agents and Rust.
I can send you daily updates on these topics — want to add anything else?"
```

If interests unclear:
```
"What kind of content do you want me to curate? Tech, product, industry news?"
```

### Step 3: Confirm schedule

Only ask what you don't know:
```
"What time works best for daily updates?"
```

Or propose a default:
```
"I'll send updates at 8am by default — OK?"
```

### Step 4: Setup + Test

1. Configure interests in `config/eir.json` (or set env vars)
2. Run `python3 scripts/standalone/curate.py`
3. **Process the output**:
   - Rank by relevance to user interests (most relevant first)
   - Translate/rewrite in user's language
   - Format as: **[Title](url)** (Source) — Summary
4. Show to user for approval
5. If approved, set up cron

### Output format

```
• **[Claude 4 Released](https://anthropic.com/...)** (Anthropic Blog)
  200K context window, native tool use, enhanced reasoning.

• **[Agent Evaluation Checklist](https://blog.langchain.com/...)** (LangChain)
  Practical agent eval checklist: error analysis, dataset construction, scorer design.
```

### Quality rules

See `references/quality-criteria.md`:
- High quality: Original research, exclusive data, S/A rated sources
- Low quality: Press releases, clickbait, thin content — skip these
- Sort by: Interest relevance > Source rating > Recency

### Example flow

```
User: "Set up daily news for me"

Agent: [checks MEMORY.md — sees "OpenClaw dev", "AI Agent"]
       [detects user language]

"Based on your recent conversations about AI Agents and dev tools, 
I'll curate content on those topics. Daily at 8am work for you?"

User: "Yeah, 8am is fine"

Agent: [runs curate.py, shows preview]
"Here's today's preview:
• Claude 4.6 Jailbroken — Public jailbreak method on GitHub
• ctx: Agentic Development Environment — New AI dev environment

Look good? I'll set up the daily schedule."

User: "Looks good"

Agent: [sets up cron]
"Done. You'll get updates every day at 8am."
```

---

## Technical Setup

### Step 1: Initialize config

Create `config/eir.json` in your skill directory (or set `EIR_CONFIG` env var to a custom path):

```json
{
  "interests": ["AI", "product design", "developer tools"],
  "language": "en",
  "max_items": 5,
  "sources": []
}
```

**interests**: Topics you care about. Will be enriched from conversation analysis.
**language**: `en` or `zh`. Auto-detected from your OpenClaw conversations if omitted.
**max_items**: Items per curation cycle.
**sources**: RSS feeds (optional). If empty, uses web search only.

### Step 2: Add RSS sources (optional)

Edit `config/eir.json` to add feeds:

```json
{
  "interests": ["AI", "product design"],
  "language": "en",
  "max_items": 5,
  "sources": [
    {"name": "Hacker News", "url": "https://hnrss.org/frontpage", "type": "rss"},
    {"name": "TechCrunch AI", "url": "https://techcrunch.com/category/artificial-intelligence/feed/", "type": "rss"}
  ]
}
```

Find RSS feeds: most blogs have `/feed`, `/rss`, or `/atom.xml`. Use `curl -s <url> | head` to verify.

## Run curation

### Manual run

```bash
# From skill directory
cd /path/to/eir-daily-content-curator
python3 scripts/standalone/curate.py
```

Output goes to stdout as JSON. Agent should format and send via `message` tool.

### What happens

1. **Load interests** from `config/eir.json` (or env vars)
2. **Fetch RSS** feeds (if configured)
3. **Search web** for each interest topic (uses Tavily if `TAVILY_API_KEY` set, else Brave if `BRAVE_API_KEY` set)
4. **Deduplicate** by URL (tracks seen URLs in `data/seen.json`)
5. **Generate summaries** for top items
6. **Output JSON** array of items

### Example output

```json
[
  {
    "title": "Claude 4 Released: 200K Context Window",
    "summary": "Anthropic releases next-gen model with longer context and tool use support.",
    "url": "https://anthropic.com/news/claude-4",
    "source": "Anthropic Blog",
    "published": "2026-04-03T10:00:00Z"
  }
]
```

## Schedule daily curation

```bash
# Add cron job (pick a random minute, not :00)
openclaw cron add --name "daily-news" \
  --cron "17 8 * * *" \
  --tz "Asia/Shanghai" \
  --message "cd $SKILL_DIR && python3 scripts/standalone/curate.py | Format each item as: **title** - summary (source) url. Send to me."
```

Or simpler — let the agent figure it out:

```bash
openclaw cron add --name "daily-news" \
  --cron "17 8 * * *" \
  --tz "Asia/Shanghai" \
  --message "Run eir-daily-content-curator skill and send me the curated content"
```

The agent will:
1. Run `curate.py`
2. Format the JSON output
3. Send via your default channel (Telegram/Discord/etc.)

## Update interests from conversations

Analyze recent OpenClaw conversations to extract interests:

```bash
python3 scripts/standalone/extract_interests.py
```

This scans `~/.openclaw/sessions/` for recent conversations and updates `config.json` with discovered topics.

**Note**: If no conversations found, add interests manually to `config.json`.

## Commands reference

| Command | Description |
|---------|-------------|
| `python3 scripts/standalone/curate.py` | Run one curation cycle |
| `python3 scripts/standalone/curate.py --dry-run` | Show what would be fetched (no output) |
| `python3 scripts/standalone/extract_interests.py` | Update interests from conversations |
| `cat config/eir.json` | View current config |
| `cat data/seen.json` | View seen URLs (dedup cache) |

## Environment variables

| Variable | Required | Description |
|----------|----------|-------------|
| `EIR_API_URL` | For Eir mode | Eir API base URL (e.g. `https://api.heyeir.com`) |
| `EIR_API_KEY` | For Eir mode | API key from pairing |
| `EIR_CONFIG` | No | Custom config file path (default: `config/eir.json`) |
| `TAVILY_API_KEY` | No | Tavily search API key (recommended) |
| `BRAVE_API_KEY` | No | Brave search API key (fallback) |

For standalone mode, only `TAVILY_API_KEY` or `BRAVE_API_KEY` is needed.
For Eir mode, set `EIR_API_URL` and `EIR_API_KEY` (or configure in `config/eir.json`).

## Cron Schedule

> **⚠️ Stagger your schedules.** Avoid running jobs on the hour (`:00`). Pick a
> random minute offset (e.g. `:07`, `:23`, `:41`) to spread load on the Eir API.

### Standalone

```bash
# Daily curation — pick a random minute, e.g. 08:17
openclaw cron add --name "daily-curate" --cron "17 8 * * *" --tz "$YOUR_TZ" \
  --message "Run eir-daily-content-curator skill and send me the curated content"
```

### Eir (Full Pipeline)

The pipeline has 6 stages. RSS and search only index title+snippet (fast, no crawl).
`content_curator` merges all candidates, picks hot topics, and crawls full text only for top matches.

```bash
# 0. Interest enrichment (once/day)
openclaw cron add --name "eir-enrich" --cron "53 3 * * *" --tz "$YOUR_TZ" \
  --message "cd $WORKSPACE && python3 scripts/pipeline/interest_extractor.py --pull --decay"

# 1. Daily plan (once/day)
openclaw cron add --name "eir-plan" --cron "23 4 * * *" --tz "$YOUR_TZ" \
  --message "cd $WORKSPACE && python3 scripts/pipeline/daily_plan.py"

# 2. RSS index (4x/day — fast, title+snippet only)
openclaw cron add --name "rss-crawl" --cron "23 5,11,17,23 * * *" --tz "$YOUR_TZ" \
  --message "cd $WORKSPACE && python3 scripts/pipeline/rss_crawler.py --max-time 120"

# 3. Search index (4x/day — fast, title+snippet only)
openclaw cron add --name "search-harvest" --cron "43 5,11,17,23 * * *" --tz "$YOUR_TZ" \
  --message "cd $WORKSPACE && python3 scripts/pipeline/search_harvest.py --max-time 120"

# 4. Content curation — merge, decide hot topics, crawl full text (3x/day)
openclaw cron add --name "content-curator" --cron "23 6,14,20 * * *" --tz "$YOUR_TZ" \
  --message "cd $WORKSPACE && python3 scripts/pipeline/content_curator.py --max-time 300"

# 5. Content generation + post (3x/day)
openclaw cron add --name "eir-generate" --cron "53 6,14,20 * * *" --tz "$YOUR_TZ" --timeout 900 \
  --message "Run generate_dispatcher.py, then for each task spawn a subagent to generate content, then run post_content.py"

# 6. Whisper extraction (daily)
openclaw cron add --name "eir-whisper" --cron "23 22 * * *" --tz "$YOUR_TZ" \
  --message "cd $WORKSPACE && python3 scripts/pipeline/whisper_extract.py"
```

## Troubleshooting

| Issue | Solution |
|-------|----------|
| No items generated | Check `config/eir.json` has interests. Add RSS sources. |
| RSS fetch fails | Verify URL with `curl -s <url> \| head`. Some sites block bots. |
| Duplicates appearing | Delete `data/seen.json` to reset dedup cache. |
| Wrong language | Set `"language": "en"` or `"zh"` in config. |

## Eir mode (optional)

Connect to [heyeir.com](https://www.heyeir.com) for enhanced features:

- Multi-source synthesis (combines 2-5 articles)
- Deep-dive analysis (L2 content)
- Beautiful reading experience
- Whisper journaling

Setup: Get pairing code from Eir Settings → Connect OpenClaw, then:

```bash
node scripts/connect.mjs <pairing-code>
```

See `references/eir-api.md` for full API documentation.
