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

## Modes

**Eir mode** — Full AI-powered curation (requires heyeir.com account)
- Learns interests from conversations
- 5-step pipeline: plan → search → select → crawl → generate+post
- Content delivered to the Eir app

**Standalone mode** — Simple RSS aggregation
- Reads tech news from RSS feeds
- Delivers summaries directly in chat
- No account needed

---

## Interest Sync (Eir mode)

Before running the content pipeline each day, sync user interests from recent conversations. This ensures curation directives reflect what the user actually cares about.

### How It Works

1. **Fetch existing interests** — `GET /oc/interests` to see what's already tracked
2. **Analyze recent conversations** — review the past 24h of user chat sessions for genuine interest signals (curiosity, deep questions, repeated engagement — not routine tool usage or one-off tasks)
3. **Extract and generalize** — map specific topics to searchable public labels (see `references/interest-extraction-prompt.md` for the full extraction prompt and rules)
4. **Submit new interests** — `POST /oc/interests/add` with deduplicated labels in the user's primary language

### Setting Up the Cron Job

Schedule interest sync to run **before** the daily content curation job (e.g., 30 minutes earlier):

```bash
openclaw cron add \
  --name "interest-sync" \
  --cron "30 3 * * *" \
  --tz "Asia/Shanghai" \
  --message "Run interest sync: read references/interest-extraction-prompt.md from the eir-daily-content-curator skill, then follow its steps — fetch current interests from GET /oc/interests, analyze recent conversations for new interest signals, and POST /oc/interests/add for any new topics discovered."
```

Adjust the schedule so it completes before your content curation cron fires.

### Cron Prompt Guidelines

The cron message should instruct the agent to:
- Load `references/interest-extraction-prompt.md` from this skill for extraction rules
- Call `GET /oc/interests` to check existing interests
- Review recent conversation sessions (past 24h) for interest signals
- Call `POST /oc/interests/add` with any new labels discovered
- Skip if no new interests are found

### Testing

Run manually first to verify the flow works:
1. Read `references/interest-extraction-prompt.md`
2. Call `GET /oc/interests` and note current list
3. Review a few recent conversations
4. Identify any new interests and call `POST /oc/interests/add`
5. Verify with `GET /oc/interests` that new entries appear

---

## Quality Feedback Handling

The curation API (`GET /oc/curation`) may return a `qualityFeedback` array containing user reports about poor content quality. Each entry has:

- `contentId` — the specific content item
- `contentGroup` — the content group identifier  
- `slug` — the anchor topic slug
- `label` — the topic display label
- `createdAt` — timestamp of the feedback

When `qualityFeedback` is present in the curation response:
1. Review the reported content groups to understand what the user found low quality
2. Consider adjusting search strategy for those topics (different sources, stricter selection criteria)
3. Log the feedback for trend analysis — if a topic consistently gets quality complaints, it may need different search hints or source preferences
4. The feedback is automatically consumed (deleted from server) after being returned once — no action needed to clear it

Note: Only private (user-specific) content quality feedback is surfaced here. Public content quality reports are recorded server-side separately.

---

## Eir Mode Pipeline

### Architecture (2-Job Split)

The pipeline runs as two separate cron jobs to avoid context overflow:

```
Job A: eir-material-prep (07:00)
  plan    → fetch directives from API (topics + search hints)
  search  → SearXNG (news-first, general fallback, web_search supplement)
  select  → cluster by topic, LLM judges candidates + generates content_slug
  crawl   → fetch full article text for selected candidates
  pack    → bundle each candidate into self-contained task file
  Output: data/v9/tasks/{content_slug}.json

Job B: eir-content-gen (07:45)
  For each task file → spawn isolated subagent (serial, one at a time):
    read task → generate content (LLM) → validate → POST to API
  Output: content posted to Eir API
```

**Why split?** A single job doing search→select→crawl→generate would accumulate too much context by generation time, causing timeouts and degraded content quality. The task files serve as a clean handoff boundary.

### Running the Pipeline

```bash
# Search (fetches directives automatically, then searches)
python3 -m pipeline.search
python3 -m pipeline.search --topic ai-agents   # single topic
python3 -m pipeline.search --dry-run            # preview queries

# Select candidates (clusters results, writes prompt for LLM)
python3 -m pipeline.candidate_selector
python3 -m pipeline.candidate_selector --dry-run

# Crawl (fetches full text for selected candidate URLs)
python3 -m pipeline.crawl
python3 -m pipeline.crawl --dry-run

# Pack tasks (bundles candidates into self-contained task files)
python3 -m pipeline.pack_tasks
python3 -m pipeline.pack_tasks --dry-run

# Validate generated content before POST
python3 -m pipeline.validate_content           # check all
python3 -m pipeline.validate_content --fix      # auto-fix \n and topicSlug
python3 -m pipeline.validate_content --file X   # check one file
```

**Generate + POST** is agent-driven. Each task file contains everything needed:
- Writer prompt
- Source material (crawled snippets)
- Candidate metadata (topic, angle, reason)

The content-gen job spawns one subagent per task **serially** (one at a time, wait for completion before next). Do NOT use sessions_yield or batch spawning.

### Task File Format

Each `data/v9/tasks/{content_slug}.json` contains:
```json
{
  "task_version": 1,
  "content_slug": "coreweave-anthropic-cloud-deal",
  "topic_slug": "ai-industry-news",
  "suggested_angle": "CoreWeave's $12B cloud deal with Anthropic",
  "writer_prompt": "...(full writer prompt)...",
  "source_text": "...(crawled article content)...",
  "source_meta": [{"url": "...", "title": "...", "name": "..."}]
}
```

### Content Slug

The `content_slug` is generated by the LLM during candidate selection:
- Descriptive, kebab-case, 3-6 words (e.g. `coreweave-anthropic-cloud-deal`)
- Based on the specific article content, not the directive topic
- Used as both the task filename and the content ID in the API

### Content Quality

See `references/content-spec.md` for full field constraints. Key rules:
- `dot.hook` ≤10 CJK chars / ≤6 EN words
- `dot.category`: `focus` | `attention` | `seed` | `whisper`
- `l1.bullets` 3-4 items, each ≤20 CJK chars
- `sources` must have at least 1 entry
- Never set any field to `null` — use `""` or `[]`
- Source attribution in `sources[]`, never inline in prose
- Only generate zh (no translation)

**Pre-POST validation** (`pipeline/validate_content.py`) runs automatically inside `post_to_api()`. It blocks POST on:
- Missing required fields (`lang`, `dot`, `l1.title`, `sources`)
- Invalid enum values (`dot.category`)
- Literal `\n` in `l2.content` (must be real newlines)
- `topicSlug` mismatch with task's `topic_slug`
- `null` values anywhere

Use `--fix` to auto-repair fixable issues (escaped newlines, topicSlug).

### Writer Prompt

Loaded from `references/writer-prompt-eir.md`. Full field spec in `references/content-spec.md`.

---

## Setup

When user says "set up daily news" or similar:

### 1. Check current setup
```bash
python3 scripts/setup.py --check
```

### 2. Choose mode
Ask user: **Standalone** (simple RSS) or **Eir** (full AI curation, requires heyeir.com account)?

### 3. Collect settings

| Setting | Default |
|---------|---------|
| Language | Auto-detect |
| Max items/day | 5 |
| Search provider | Tavily or Brave (standalone), SearXNG (self-hosted) |

For Eir mode, connect account: `node scripts/connect.mjs <PAIRING_CODE>`

### 4. Initialize
```bash
python3 scripts/setup.py --init --settings '<json>'
```

### 5. Set schedule
```bash
openclaw cron add --name "eir-daily" --cron "0 8 * * *" --tz "Asia/Shanghai" \
  --session isolated --message "Run eir-daily-content-curator pipeline"
```

### 6. Test run
- Standalone: `python3 scripts/standalone/curate.py`
- Eir: run the pipeline steps above

---

## Quick Reference

| Task | Command |
|------|---------||
| Interest sync | Agent-driven (see Interest Sync section above) |
| Check setup | `python3 scripts/setup.py --check` |
| Search | `python3 -m pipeline.search` |
| Select candidates | `python3 -m pipeline.candidate_selector` |
| Crawl | `python3 -m pipeline.crawl` |
| Pack tasks | `python3 -m pipeline.pack_tasks` |
| Standalone curate | `python3 scripts/standalone/curate.py` |

### Infrastructure

Self-hosted search and crawl services are optional fallbacks. The pipeline defaults to the configured Grounding API (Brave, Tavily, or similar).

### References

| File | Contents |
|------|----------|
| `references/content-spec.md` | Field types, limits, validation rules |
| `references/eir-api.md` | API endpoints and payloads |
| `references/writer-prompt-eir.md` | Content generation prompt |
| `references/writer-prompt-standalone.md` | Standalone mode prompt |
| `references/eir-interest-rules.md` | Curation tier guidelines |
| `references/whisper-api.md` | Whisper extraction API |
| `references/whisper-writer-prompt.md` | Whisper generation prompt |

### Version Check

Before running pipeline, verify schema compatibility:
1. Read `schema_version` from `GET /oc/curation`
2. Compare against `supported_schema_versions` in `config/settings.json`
3. Major version changes require skill update

### RSS Sources

Add feeds to `config/sources.json`:
```json
{
  "name": "Example Blog",
  "url": "https://example.com/feed.xml",
  "rating": "A",
  "lang": "en"
}
```
Ratings: S (4h), A (8h), B (24h).
