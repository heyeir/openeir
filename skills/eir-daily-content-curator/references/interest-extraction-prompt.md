# Interest Extraction Prompt

> Used by the OpenClaw agent to discover interests from conversations and add them to Eir.

## Your Job

Analyze user conversations → extract genuine interests.

**Standalone mode**: Save to `config/interests.json`
**Eir mode**: `POST /oc/interests/add` with labels

**You decide WHAT the user is interested in.**

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

### 1. Read current interests

**Standalone**: Read `config/interests.json` — see what's already tracked.
**Eir**: `GET /oc/interests` — see what's already tracked.

Don't add duplicates.

### 2. Analyze conversations
Look for genuine interest signals — curiosity, depth, repeated engagement.

### 3. Generalize to searchable topics
Private contexts → universal, publicly-searchable labels.

| ❌ Too specific | ✅ Good label |
|-----------------|---------------|
| "Meta UTIS paper" | Recommendation Systems |
| "Our Cosmos DB migration" | Database Architecture |
| "Debugging our RAG pipeline" | AI Retrieval & RAG |

### 4. Submit new interests

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

Use `primary_language` from user profile for label language.

## Rules

1. **Quality over quantity** — 1-3 genuine interests per session, not 10 vague ones
2. **Content-value test** — every label must match quality external content. "Our internal API" fails this test
3. **Use primary_language** for labels (usually "zh" or "en")
4. **Don't duplicate** — check GET /oc/interests first
5. **Broad enough to be useful** — "AI" is too broad, "GPT-4o mini tokenizer bug" is too narrow
6. **Respect user privacy** — generalize private details into public topics

## Relationship to Content Interest Signals

Interest extraction from conversations is separate from the `interests.anchor` and `interests.related` fields on content items.

- **This prompt**: discovers interests from user conversations → `POST /oc/interests/add`
- **Content interests**: declared by the content writer when generating content → `interests.anchor` + `interests.related` on `POST /oc/content`

Both feed into the same interest system. Extracted interests may later appear as valid anchor targets in curation directives.
