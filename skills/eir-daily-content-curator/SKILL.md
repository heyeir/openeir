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

When user says "set up daily news" or similar, follow this conversational flow. **Ask before doing** — explain what you're about to do and wait for confirmation.

### Step 1: Check existing setup

First, check if already configured:
```bash
python3 scripts/setup.py --check
```

If already set up, skip to [Step 4: Test run](#step-4-test-run).

### Step 2: Explain the two modes

**Ask user which mode they want:**

> "I can set up daily content curation in two ways:
> 
> **Option A: Standalone** — Simple RSS aggregation
> • Reads tech news from RSS feeds
> • Delivers summaries directly here
> • No account needed, works immediately
> 
> **Option B: Eir** — Full AI-powered curation (requires heyeir.com account)
> • Learns your interests from conversations
> • Personalized content with deep-dive analysis
> • Reads in the Eir app with beautiful formatting
> 
> Which would you prefer?"

### Step 3: Run setup wizard (with user)

**Say:**
> "I'll run the setup wizard now. It will ask about:
> • Where to store your config (default: ~/.openclaw/skills/eir/)
> • Your timezone and preferred language
> • When you want content delivered
> 
> Ready?"

**Wait for confirmation, then run:**
```bash
python3 scripts/setup.py
```

**Guide user through each prompt** — follow this rule:

| Setting | Source | Agent Action |
|---------|--------|--------------|
| **Language** | Auto-detect from conversation | "I'll use Chinese based on our conversation" |
| **Timezone** | Auto-detect from system | "I'll use Asia/Shanghai (detected from your system)" |
| **Workspace** | Default `~/.openclaw/skills/eir/` | "Press Enter for default, or specify a different path" |
| **Mode** | User already chose in Step 2 | Pre-fill their choice |
| **Search API key** | **Must ask** | "Enable web search? Requires Tavily/Brave API key" |
| **Infrastructure** | **Must ask** | "Have you set up SearXNG/Crawl4AI? (optional, see docs)" |
| **Schedule** | **Must ask** | "What time for daily delivery?" |

**Never assume for:** API keys, infrastructure setup, schedule preferences.

### Step 4: Propose cron schedule

**After setup completes, propose a schedule:**

> "Setup complete! Now for the delivery schedule.
> 
> I recommend:
> • **Morning briefing**: 8:00 AM daily
> • **Frequency**: Once per day (adjustable)
> • **Timezone**: Asia/Shanghai
> 
> Does that work? Or would you prefer a different time?"

**If user confirms, set up cron:**
```bash
openclaw cron add --name "eir-daily" --cron "0 8 * * *" --tz "Asia/Shanghai" --message "Run daily curation"
```

**If user wants different time:**
> "What time would you prefer? (e.g., 7am, 9:30am, evening 8pm)"

**Convert their answer to cron:**
- "7am" → `0 7 * * *`
- "9:30am" → `30 9 * * *`
- "evening" → `0 20 * * *`

**Always confirm before creating:**
> "I'll set it for 9:30 AM daily. Confirm?"

### Step 5: Test run

**Say:**
> "Let me fetch today's preview so you can see what it looks like. One moment..."

**Run:**
```bash
python3 scripts/standalone/curate.py
```

**Format and present:**
> "Here's what today's curation looks like:
> 
> • **Claude 4 Released** (Anthropic Blog)
>   200K context window, native tool use...
>   https://...
> 
> • **Agent Evaluation Checklist** (LangChain)
>   Practical checklist for eval design...
>   https://...
> 
> This is the format you'll receive daily. Look good?"

**If user says yes:**
> "Perfect! You're all set. You'll receive your first update tomorrow at [time].
> 
> To change anything later, just ask me to 'update news settings'.
> To pause: 'pause daily news'
> To get a preview anytime: 'show me today's news'"

**If user wants changes:**
> "What would you like to adjust? The topics, sources, or delivery time?"

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

---

## Example Conversation

### Scenario 1: First-time setup

```
User: "Can you set up daily news for me?"

Agent: "I can set up daily content curation in two ways:

**Option A: Standalone** — Simple RSS aggregation
• Reads tech news from RSS feeds  
• Delivers summaries directly here
• No account needed

**Option B: Eir** — Full AI-powered curation  
• Learns your interests from conversations
• Personalized content with deep-dive analysis
• Reads in the Eir app

Which would you prefer?"

User: "Option A sounds good"

Agent: "Great! I'll run the setup wizard. It will ask about workspace location, 
timezone, and schedule. Ready?"

User: "Sure"

Agent: [runs setup.py, guides through prompts]
"Setup complete! Now for the schedule — I recommend 8:00 AM daily. 
Does that work, or would you prefer a different time?"

User: "8am is fine"

Agent: [creates cron job]
"Done! Let me fetch a preview of what you'll receive..."

Agent: [runs curate.py, shows sample]
"Here's today's preview:
• Claude 4.6 Jailbroken — Public jailbreak on GitHub
• ctx: Agentic Development Environment — New AI dev environment

This is the format you'll get daily. Look good?"

User: "Looks good"

Agent: "Perfect! You'll receive your first update tomorrow at 8am. 
To change anything, just say 'update news settings'."
```

### Scenario 2: User wants to change time

```
User: "Can you move my news to 9am?"

Agent: "Sure, I'll update your schedule from 8am to 9am. Confirm?"

User: "Yes"

Agent: [updates cron job]
"Done! Your daily news will now arrive at 9:00 AM."
```

### Scenario 3: User wants to pause

```
User: "Pause my daily news"

Agent: "I'll pause your daily curation. You can resume anytime by saying 
'resume daily news'. Confirm?"

User: "Yes"

Agent: [disables cron job]
"Paused. Your settings are saved — just say 'resume daily news' when you want it back."
```

---

## Quick Reference (For Agent)

### Commands

| Task | Command |
|------|---------|
| Check setup | `python3 scripts/setup.py --check` |
| Run setup wizard | `python3 scripts/setup.py` |
| Test curation | `python3 scripts/standalone/curate.py` |
| Add cron | `openclaw cron add --name "eir-daily" --cron "0 8 * * *" --tz "Asia/Shanghai" --message "..."` |
| List cron | `openclaw cron list` |
| Disable cron | `openclaw cron edit <id> --enabled=false` |

### Cron Schedule Examples

| User says | Cron expression |
|-----------|-----------------|
| "8am" | `0 8 * * *` |
| "9:30am" | `30 9 * * *` |
| "evening 8pm" | `0 20 * * *` |
| "midnight" | `0 0 * * *` |
| "weekends only" | `0 9 * * 6,7` |

### Mode Differences

| Feature | Standalone | Eir |
|---------|-----------|-----|
| Account needed | No | Yes (free) |
| Interest learning | Manual | Automatic |
| Content source | RSS + search | RSS + search + API |
| Delivery | OpenClaw chat | OpenClaw + Eir app |
| Personalization | Basic | Advanced |

---

## Manual Setup (Advanced)

If you prefer to configure manually instead of using the wizard:

### Prerequisites

- **Python 3.10+** with `sentence-transformers`, `numpy`, `tzlocal`
- **Node.js 18+** (for Eir connection)
- **Optional**: SearXNG, Crawl4AI, Search Gateway (see `references/infrastructure-setup.md`)

```bash
pip install sentence-transformers numpy tzlocal
```

### Step 1: Choose Your Mode

**Standalone Mode** — Simple RSS aggregation, no Eir account needed
- Uses local RSS feeds + optional web search (Tavily/Brave APIs)
- Content delivered directly to you via OpenClaw

**Eir Mode** — Full AI curation with heyeir.com
- Personalized content based on your interest profile
- Multi-source synthesis and deep-dive analysis
- Beautiful reading experience in the Eir app

### Step 2a: Standalone Setup

Create `config/settings.json`:

```json
{
  "mode": "standalone",
  "max_items_per_day": 5,
  "search": {
    "providers": ["tavily"],
    "tavily_api_key": "your-key-here"
  },
  "cron": {
    "schedule": "0 8 * * *",
    "timezone": "Asia/Shanghai"
  }
}
```

Get a Tavily API key: https://tavily.com (free tier available)

### Step 2b: Eir Setup

1. **Get a pairing code** from Eir app → Settings → Connect OpenClaw

2. **Connect your account**:
   ```bash
   node scripts/connect.mjs ABCD-1234
   ```
   This creates `config/eir.json` with your API credentials.

3. **Configure settings**:
   ```bash
   python3 scripts/setup.py  # Interactive
   # or manually edit config/settings.json
   ```

   Key settings for Eir mode:
   ```json
   {
     "mode": "eir",
     "eir": {
       "bilingual": false,
       "primary_language": "zh"
     }
   }
   ```

### Step 3: Verify Setup

```bash
# Check configuration
python3 scripts/setup.py --check

# Test standalone curation
python3 scripts/standalone/curate.py

# Test Eir connection (if in eir mode)
python3 scripts/pipeline/interest_extractor.py --stats
```

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

The pipeline has 7 stages. RSS and search only index title+snippet (fast, no crawl).
`content_curator` merges all candidates, picks hot topics, and crawls full text only for top matches.
`daily_plan` also runs `pool_pruner` at startup to clean stale/used pool entries.

#### Pipeline scripts

| Script | Role |
|--------|------|
| `interest_extractor.py` | Sync interests with Eir API + local topic enrichment |
| `daily_plan.py` | Daily plan: RSS config + API directives + enrichment → `daily_plan.json`. Runs `pool_pruner` first. |
| `rss_crawler.py` | RSS fetch → title+snippet embedding → topic matching |
| `search_harvest.py` | Web search via Search Gateway → title+snippet embedding → topic matching |
| `content_curator.py` | Merge RSS+search candidates, rank by score+freshness, crawl full text for top picks → `curation_result.json` |
| `generate_dispatcher.py` | Composite scoring to select topics → spawn subagent for content generation |
| `post_content.py` | Read generated JSON → POST L1 + PATCH L2 to Eir API |
| `deliver.py` | Save content locally + send notifications; in Eir mode also calls `post_content.py` |
| `pool_pruner.py` | Clean expired/used/orphan pool entries from `topic_matches.json` |
| `title_dedup.py` | L1 semantic dedup (cosine ≥ 0.82) |
| `embed.py` | EmbeddingGemma-300M wrapper (encode, cosine, meta) |
| `cache_manager.py` | Article embed cache + snippet storage |

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
  --message "Run generate_dispatcher.py, then for each task spawn a subagent to generate content, then run deliver.py"

# 6. Whisper extraction (daily, optional)
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
| Pool saturated (topic skipped) | Pool has ≥10 active articles. Wait for generation to consume them, or run `pool_pruner.py` to clean stale entries. |
| Pool empty after pruning | Check RSS/search are running and `source_freshness_floor` isn't too aggressive for the topic's `freshness` setting. |

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

For Eir mode, change `mode` to `"eir"` in `config/settings.json`:

```json
{
  "mode": "eir",
  "search": {
    "providers": ["searxng"],
    "searxng_url": "http://localhost:8888",
    "crawl4ai_url": "http://localhost:11235"
  }
}
```

See `references/eir-api.md` for full API documentation.

### Infrastructure (self-hosted search & crawl)

The Eir pipeline can use local services instead of Tavily/Brave for better coverage and no API rate limits:

| Service | Purpose | Default URL |
|---------|---------|-------------|
| [SearXNG](https://github.com/searxng/searxng) | Meta-search (Google + Bing + Brave in one query) | `http://localhost:8888` |
| [Crawl4AI](https://github.com/unclecode/crawl4ai) | Full-article extraction as clean markdown | `http://localhost:11235` |
| Search Gateway | Thin wrapper over SearXNG with engine routing | `http://localhost:8899` |
| [EmbeddingGemma-300M](https://huggingface.co/google/embeddinggemma-300m) | Semantic dedup & topic matching (256d, CPU-friendly) | Local Python |

All are **optional** — standalone mode uses Tavily/Brave instead.

For detailed installation and configuration, see `references/infrastructure-setup.md`.
