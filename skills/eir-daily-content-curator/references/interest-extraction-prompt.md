# Interest Extraction Prompt

> Used by main agent's interest-sync cron to update the reader profile and interest system.

## Your Job

Analyze user activity → Extract genuine interests and context → Update USER.md + submit to interest system.

**You decide WHAT the user is interested in and WHO they are becoming.**

## Core Principle: Infer Interests from Behavior

The user's work reveals what they want to READ about — not what they're building.

Ask: *"Someone doing this work — what public content would they find valuable?"*

### Examples

| User is doing... | Interest to extract |
|-------------------|---------------------|
| Building a RAG pipeline | AI retrieval systems, vector databases |
| Debugging CSS grid layout | ❌ Not an interest (just a task) |
| Researching MCP protocol excitedly | MCP Protocol, AI agent infrastructure |
| Complaining about Vercel cold starts | ❌ Not an interest (complaint, not curiosity) |
| Asking deep questions about embeddings | Embedding models, semantic search |
| Discussing interior design for new home | Interior design, spatial design |

### What IS an interest
- Topics they ask deep questions about
- Domains they spend time researching (not just using)
- Areas where they express curiosity, excitement, or strong opinions
- Subjects they want to stay updated on

### What is NOT an interest
- Tools they use mechanically (git, npm, etc.)
- One-off debugging tasks
- Complaints without curiosity
- Things already well-known to them (no new content needed)

## Extraction Steps

### 1. Read USER.md
Read the content workspace `USER.md` — this is the reader profile that content generation reads. It lives at the path specified in the cron prompt.

Also read main agent's `USER.md` (workspace/USER.md) for richer context about work style, communication preferences, and API notes — but **don't copy those sections** into the content USER.md.

### 2. Analyze recent activity
Review the user's recent interactions and work context.

Look for:
- **Interest signals** — curiosity, depth, repeated engagement with a topic
- **Context signals** — role changes, new projects, new tools adopted
- **Focus shifts** — what's consuming attention this week vs last month
- **Perspective signals** — strong opinions, frameworks, mental models expressed

### 3. Generalize to searchable topics
Private contexts → universal, publicly-searchable labels.

| ❌ Too specific | ✅ Good label |
|-----------------|---------------|
| "Meta UTIS paper" | Recommendation Systems |
| "Our Cosmos DB migration" | Database Architecture |
| "Debugging our RAG pipeline" | AI Retrieval & RAG |

### 4. Update USER.md

The content USER.md has this structure:

```markdown
# USER.md — Reader Profile

- **Name:** ...
- **Timezone:** ...
- **Languages:** zh (primary), en (native-level reading)

## Role & Context
- [What they do, what they're building]
- [Current org/team context]

### Current Focus (YYYY-MM)
- [What's consuming attention right now — update monthly]

## Interests
- [Active interests — topics they want content about]

## Perspective
- [How they think, what they value, what makes content land for them]
```

**Update rules:**
- **Current Focus** — replace items that are done/stale, add new ones. Date the section header (YYYY-MM)
- **Interests** — target 8-15 items. Add new ones, **demote stale ones** (no signal in 30+ days → remove to make room)
- **Role & Context** — only update on significant changes (new product, role shift)
- **Perspective** — only update when conversations reveal a new mental model or value shift
- **Keep it concise** — total file should stay under ~50 lines
- **Merge similar items** — don't let lists bloat with near-duplicates
- **Don't over-infer** — only add things with clear signal from conversations

### 5. Submit interests to system

**Eir mode** — POST to API:
```
POST {EIR_API_URL}/oc/interests/add
Authorization: Bearer {EIR_API_KEY}

{
  "labels": ["AI Retrieval & RAG", "Embedding Models"],
  "lang": "en"
}
```

**Standalone mode** — update `config/interests.json`:
```json
{
  "topics": [
    {"label": "AI Retrieval & RAG", "keywords": ["RAG", "vector search", "retrieval"], "freshness": "7d"},
    {"label": "Embedding Models", "keywords": ["embeddings", "semantic search"], "freshness": "7d"}
  ],
  "language": "en",
  "max_items_per_day": 8
}
```

## Rules

1. **Quality over quantity** — 1-3 genuine new interests per sync, not 10 vague ones
2. **Content-value test** — every label must match quality external content
3. **Don't duplicate** — check USER.md interests first
4. **Broad enough to be useful** — "AI" is too broad, "GPT-4o mini tokenizer bug" is too narrow
5. **Respect user privacy** — generalize private details into public topics
6. **USER.md is the source of truth** — content generation reads this to personalize output
7. **Demote stale interests** — if an interest has no signal in 30+ days, remove it to keep the list fresh
8. **Bilingual labels OK** — use the language that matches the best public content for that topic
