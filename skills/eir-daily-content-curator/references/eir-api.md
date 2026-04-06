# Eir API Reference

> **Base URL**: `https://api.heyeir.com/api`
>
> **Authentication**: All `/oc/*` endpoints require `Authorization: Bearer <EIR_API_KEY>` header.
>
> **Credential storage** (OpenClaw):
> ```bash
> openclaw config set skills.entries.eir-daily-content-curator \
>   '{"enabled":true,"env":{"EIR_API_URL":"https://api.heyeir.com/api","EIR_API_KEY":"<key>"}}' \
>   --strict-json
> ```

---

## Connection

### POST /oc/connect

Register with a pairing code. No API key needed (this is how you get one).

**Request:** `{ "code": "ABCD-1234" }`

**Response:** `{ "apiKey": "eir_oc_xxx", "userId": "u_abc123", "status": "connected" }`

### DELETE /oc/connect

Disconnect. Revokes the API key.

### POST /oc/refresh-key

Rotate API key. Old key valid for 60s grace period.

**Response:** `{ "apiKey": "eir_oc_new_xxx", "rotatedAt": "...", "prevKeyExpiresAt": ... }`

---

## Interests

### GET /oc/interests

Returns user interests in v3 format.

**Response:**
```json
{
  "user": { "id": "u_xxx", "locale": "zh", "primary_language": "zh", "bilingual": false },
  "interests": [
    {
      "id": "ui_abc1234",
      "slug": "artificial-intelligence",
      "label": "人工智能",
      "source": "content_interest",
      "status": "active",
      "heat": 5,
      "strength": 0.6,
      "createdAt": 1775467481053,
      "lastActiveAt": 1775467481053
    }
  ]
}
```

### POST /oc/interests/add

Add interests by label. Server matches against the topic dictionary.

**Request:**
```json
{
  "labels": ["AI Agents", "MCP Protocol"],
  "lang": "en"
}
```

**Response:** `{ "added": 2, "results": [...] }`

Matched labels get a `slug` and `status: "active"`. Unmatched labels get `slug: null` and `status: "unknown"` (flagged for admin review).

---

## Curation

### GET /oc/curation

Returns curation directives for today's content collection.

**Response:**
```json
{
  "user": { "primary_language": "zh", "bilingual": false },
  "schema_version": "2",
  "tracked": [
    {
      "slug": "mcp-protocol",
      "topic": "MCP Protocol",
      "description": "...",
      "keywords": ["MCP", "model context protocol"],
      "search_hints": ["MCP 2.0", "Anthropic MCP"],
      "strength": 0.9,
      "engagement_health": 1.1,
      "priority": "high",
      "max_items": null,
      "quality_threshold": 0.6,
      "freshness": "7d"
    }
  ],
  "directives": [
    {
      "type": "focus",
      "slug": "ai-agents",
      "topic": "AI Agents",
      "description": "...",
      "keywords": ["..."],
      "search_hints": ["..."],
      "strength": 0.8,
      "score": 0.72,
      "engagement_health": 0.9,
      "quality_threshold": 0.7,
      "freshness": "7d"
    }
  ],
  "budget": {
    "suggested_total": 6,
    "remaining_today": 5
  },
  "exclude": {
    "disliked": ["crypto", "nft"]
  }
}
```

**Tiers:** tracked (user explicit) → focus (strong) → explore (moderate) → seed (discovery).

See `eir-interest-rules.md` for curation logic.

### GET /oc/sources

Returns already-pushed source URLs for dedup.

**Query:** `?days=7` (default: 7)

**Response:** `{ "urls": ["https://..."], "count": 12, "since": "..." }`

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
      "topicSlug": "mcp-protocol",
      "lang": "en",
      "dot": {
        "hook": "MCP 2.0 Released",
        "category": "focus",
        "color_hint": "blue"
      },
      "l1": {
        "title": "MCP Protocol v2.0",
        "summary": "Anthropic releases MCP 2.0...",
        "key_quote": "...",
        "via": ["Anthropic Blog"]
      },
      "l2": {
        "content": "...(500+ words)...",
        "bullets": [{ "text": "...", "confidence": "high" }],
        "context": "...",
        "eir_take": "...",
        "related_topics": ["ai-agents"]
      },
      "sources": [
        { "url": "https://...", "title": "...", "name": "Anthropic Blog" }
      ]
    }
  ]
}
```

**Key rules:**
- `lang` required ("en" or "zh"). API rejects `lang="en"` if hook contains CJK.
- `l1` and `l2` are top-level per item.
- For bilingual: push two separate items, same `slug`/`topicSlug`, different `lang`.
- `l1.via`: auto-derived from `sources[].name` if empty.
- Field types & limits → see `content-spec.md`.

**Response:**
```json
{
  "accepted": 1,
  "results": [
    { "status": "accepted", "id": "a3k9m2x7_en", "contentGroup": "a3k9m2x7", "slug": "mcp-protocol-2-0" }
  ]
}
```

ID format: `{8-char contentGroup}_{lang}`. All language versions share the same `contentGroup`.

### DELETE /oc/content/:id

Delete content by doc id or contentGroup (deletes all langs).

### GET /oc/content/:id

Read back a single content item.

---

## Conversations & Whispers

### GET /oc/conversations

List user conversations.

**Query:** `?limit=20&whisper_candidates=true&since=2026-04-01T00:00:00Z`

**Response:**
```json
{
  "conversations": [
    {
      "id": "conv_abc123",
      "startedAt": 1712345678000,
      "messageCount": 12,
      "preview": "First user message...",
      "whisperCandidate": true,
      "whisperReason": "Genuine insight about AI consciousness"
    }
  ]
}
```

### GET /oc/conversations/:id

Get full conversation with all messages.

### POST /oc/whispers

Create a whisper from conversation insight.

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

**Response:** `{ "ok": true, "id": "whisper_...", "whisper": { ... } }`
