# Eir API Reference

**Base URL**: `https://api.heyeir.com/api`

**Authentication**: `Authorization: Bearer <EIR_API_KEY>` for all `/oc/*` endpoints.

---

## Connection

### POST /oc/connect
Register with pairing code.

**Request:** `{ "code": "ABCD-1234" }`

**Response:** `{ "apiKey": "eir_oc_xxx", "userId": "u_abc123" }`

### DELETE /oc/connect
Disconnect and revoke API key.

### POST /oc/refresh-key
Rotate API key (60s grace period).

---

## Interests

### GET /oc/interests
Returns user interests.

**Response:**
```json
{
  "user": { "id": "u_xxx", "primaryLanguage": "zh", "bilingual": false },
  "interests": [
    {
      "id": "ui_abc1234",
      "slug": "artificial-intelligence",
      "label": "Artificial Intelligence",
      "status": "active",
      "heat": 5,
      "strength": 0.6
    }
  ]
}
```

### POST /oc/interests/add
Add interests by label. Server matches against dictionary.

**Request:** `{ "labels": ["AI Agents", "MCP"], "lang": "en" }`

**Response:** `{ "added": 2, "results": [...] }`

---

## Curation

### GET /oc/curation
Returns curation directives for content collection.

**Response:**
```json
{
  "schema_version": "1.0",
  "user": {
    "primaryLanguage": "zh",
    "bilingual": false
  },
  "directives": [
    {
      "slug": "mcp-protocol",
      "label": "MCP Protocol",
      "tier": "tracked",
      "freshness": "7d",
      "searchHints": ["MCP 2.0 announced", "Anthropic MCP ecosystem"],
      "userNeeds": "Protocol updates and adoption",
      "trackingGoal": "Stay current on protocol updates"
    },
    {
      "slug": "ai-agents",
      "label": "AI Agents",
      "tier": "focus",
      "freshness": "7d",
      "searchHints": ["AI agent frameworks comparison", "autonomous agent production"],
      "userNeeds": null,
      "trackingGoal": null
    }
  ],
  "exclude": {
    "disliked": ["crypto", "nft"]
  }
}
```

**Tiers:** tracked → focus → explore → seed (informational labels; selection is score-based).

**Server-side curation:** The API handles topic selection, cooldown, and scoring internally. The agent just reads directives and finds content for them.

See `eir-interest-rules.md` for curation guidelines.

---

## Content

### POST /oc/content
Push generated content.

**Request:**
```json
{
  "items": [
    {
      "slug": "mcp-protocol-2-0",
      "lang": "en",
      "interests": {
        "anchor": ["mcp-protocol"],
        "related": [{ "slug": "a2a-protocol", "label": "A2A Protocol" }]
      },
      "dot": {
        "hook": "MCP 2.0 Released",
        "category": "focus",
      },
      "l1": {
        "title": "MCP Protocol v2.0",
        "summary": "Anthropic releases MCP 2.0...",
        "key_quote": "..."
      },
      "l2": {
        "content": "...(500+ words)...",
        "bullets": [{ "text": "...", "confidence": "high" }],
        "context": "...",
        "eir_take": "...",
        "related_topics": ["ai-agents"]
      },
      "sources": [{ "url": "https://...", "title": "...", "name": "Anthropic Blog" }]
    }
  ]
}
```

**Rules:**
- `lang` required ("en" or "zh")
- `interests.anchor` required (1-3 slugs from curation directives). Must match user's interests.
- `interests.related` optional (max 5). Unknown topics auto-created as candidates.
- For bilingual: push two items with same `slug`, different `lang`
- See `content-spec.md` for field limits

**Response:**
```json
{
  "accepted": 1,
  "results": [{ "status": "accepted", "id": "a3k9m2x7_en", "contentGroup": "a3k9m2x7" }]
}
```

### GET /oc/content/:id
Read back a content item.

### DELETE /oc/content/:id
Delete by id or contentGroup.

### POST /oc/curation/miss
Report topics where you searched but found no quality content. This lowers their priority in future curation rounds.

**Request:** `{ "slugs": ["topic-a", "topic-b"] }`

**Response:** `{ "ok": true, "updated": 2 }`

**When to call:** After finishing a curation round, if you searched for a topic's searchHints but found nothing worth pushing.

---

## Conversations & Whispers

### GET /oc/conversations
List conversations.

**Query:** `?limit=20&whisper_candidates=true&since=2026-04-01T00:00:00Z`

### GET /oc/conversations/:id
Get full conversation.

### POST /oc/whispers
Create a whisper.

**Request:**
```json
{
  "dot": { "hook": "≤50 chars" },
  "l1": {
    "title": "Core tension",
    "summary": "80-120 words",
    "participants": "user+eir",
    "via": ["OpenClaw"]
  },
  "l2": {
    "content": "300-600 words",
    "tension": "X vs Y",
    "unresolved": "Open question",
    "thinking_path": ["node1", "node2"],
    "eir_role": "challenger|extender|mirror|catalyst",
    "related_topics": ["topic-slug"]
  },
  "conversationId": "conv_abc123",
  "source": "openclaw"
}
```
