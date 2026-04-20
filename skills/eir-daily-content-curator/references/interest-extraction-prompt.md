# Interest Extraction Prompt

> Used by the OpenClaw agent to discover interests from conversations and update the user profile.

## Your Job

Analyze user conversations → extract genuine interests and context → update USER.md + submit to interest system.

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
Read the workspace `USER.md` to understand the user's current profile, interests, and context. This is the single source of truth for who the user is.

### 2. Analyze conversations
Look for genuine interest signals — curiosity, depth, repeated engagement.
Also look for **context signals** — role changes, new projects, shifts in perspective.

### 3. Generalize to searchable topics
Private contexts → universal, publicly-searchable labels.

| ❌ Too specific | ✅ Good label |
|-----------------|---------------|
| "Meta UTIS paper" | Recommendation Systems |
| "Our Cosmos DB migration" | Database Architecture |
| "Debugging our RAG pipeline" | AI Retrieval & RAG |

### 4. Update USER.md

Update the `USER.md` file with new information. The file has these sections:

```markdown
# USER.md

- **Name:** ...
- **Timezone:** ...
- **Communication style:** ...

## Role & Context
- [What they do, what they're building]
- [Current focus areas]

## Interests
- [Active interests — topics they want content about]

## Perspective
- [How they think, what they value, what makes content land for them]
```

**Rules for updating USER.md:**
- **Append/update, never delete** existing info unless explicitly outdated
- **Keep it concise** — each section should be 3-8 bullet points max
- **Merge similar items** — don't let lists bloat with near-duplicates
- **Date major shifts** — if their role or focus changes significantly, note when
- **Don't over-infer** — only add things with clear signal from conversations

### 5. Submit interests to system

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

**Eir mode** — POST to API:
```
POST {EIR_API_URL}/oc/interests/add
Authorization: Bearer {EIR_API_KEY}

{
  "labels": ["AI Retrieval & RAG", "Embedding Models"],
  "lang": "en"
}
```

## Rules

1. **Quality over quantity** — 1-3 genuine interests per session, not 10 vague ones
2. **Content-value test** — every label must match quality external content
3. **Don't duplicate** — check USER.md interests first
4. **Broad enough to be useful** — "AI" is too broad, "GPT-4o mini tokenizer bug" is too narrow
5. **Respect user privacy** — generalize private details into public topics
6. **USER.md is the source of truth** — content generation reads this to personalize output
7. **Avoid bloat** — if USER.md exceeds ~40 lines, consolidate older/less-relevant items
