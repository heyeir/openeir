# OpenClaw Whisper API Specification

> For OpenClaw skill to extract and create Whispers from conversations.

---

## Endpoint 1: List Conversations

### `GET /api/oc/conversations`

**Purpose**: Fetch user conversations, optionally filtered to whisper candidates.

**Query Parameters**:

| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `limit` | int | No | Max results (default 20, max 50) |
| `whisper_candidates` | bool | No | Filter to conversations marked as whisper candidates |
| `since` | ISO 8601 | No | Filter to conversations started after this time |

**Headers**:
```
Authorization: Bearer {api_key}
Accept: application/json
```

**Success Response (200)**:
```json
{
  "conversations": [
    {
      "id": "conv_abc123",
      "startedAt": 1712345678000,
      "endedAt": 1712346000000,
      "messageCount": 12,
      "preview": "First user message...",
      "whisperCandidate": true,
      "whisperReason": "Genuine insight about AI consciousness"
    }
  ]
}
```

**Error Response**:
```json
// 401 Unauthorized
{ "error": "Invalid API key" }

// 403 Forbidden
{ "error": "OpenClaw access not enabled for this user" }
```

---

## Endpoint 2: Get Conversation Detail

### `GET /api/oc/conversations/:id`

**Purpose**: Fetch full conversation with all messages for analysis.

**Headers**:
```
Authorization: Bearer {api_key}
Accept: application/json
```

**Success Response (200)**:
```json
{
  "conversation": {
    "id": "conv_abc123",
    "userId": "u_xxx",
    "startedAt": 1712345678000,
    "endedAt": 1712346000000,
    "messages": [
      {"role": "user", "content": "...", "timestamp": 1712345678000},
      {"role": "assistant", "content": "...", "timestamp": 1712345680000}
    ],
    "messageCount": 12,
    "whisperCandidate": true,
    "whisperReason": "..."
  }
}
```

---

## Endpoint 3: Create Whisper

### `POST /api/oc/whispers`

**Purpose**: Create a single Whisper from extracted conversation insight.

**Headers**:
```
Authorization: Bearer {api_key}
Content-Type: application/json
```

**Request Body**:
```json
{
  "dot": {
    "hook": "≤10 character hook"
  },
  "l1": {
    "title": "Core tension description",
    "summary": "80-120 word summary",
    "participants": "user+eir",
    "via": ["OpenClaw"]
  },
  "l2": {
    "content": "300-600 word full content",
    "tension": "X vs Y",
    "unresolved": "Open question",
    "thinking_path": ["node1", "node2", "node3"],
    "eir_role": "challenger|extender|mirror|catalyst",
    "related_topics": ["topic-slug"]
  },
  "conversationId": "conv_abc123",
  "conversation_excerpt": {
    "messages": [{"role": "user", "content": "..."}],
    "total_messages": 8
  },
  "source": "openclaw"
}
```

**Field Descriptions**:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `dot.hook` | string | Yes | ≤10 character hook for dot display |
| `l1.title` | string | Yes | Core tension, one sentence |
| `l1.summary` | string | Yes | 80-120 word summary |
| `l1.participants` | string | Yes | Fixed `"user+eir"` |
| `l1.via` | string[] | Yes | `["OpenClaw"]` |
| `l2.content` | string | Yes | 300-600 word full content |
| `l2.tension` | string | Yes | Tension description (X vs Y) |
| `l2.unresolved` | string | Yes | Unresolved question |
| `l2.thinking_path` | string[] | Yes | 3-5 thinking nodes |
| `l2.eir_role` | string | Yes | `challenger`/`extender`/`mirror`/`catalyst` |
| `l2.related_topics` | string[] | No | Related topic slugs |
| `conversationId` | string | No | Source conversation ID |
| `conversation_excerpt` | object | No | Original conversation excerpt |
| `source` | string | Yes | Fixed `"openclaw"` |

**Success Response (200)**:
```json
{
  "ok": true,
  "id": "x7k2m9p4_en",
  "whisper": {
    "id": "x7k2m9p4_en",
    "contentGroup": "x7k2m9p4",
    "lang": "en",
    "userId": "u_xxx",
    "dot": { "hook": "...", "category": "whisper", "color_hint": "amber" },
    "l1": { ... },
    "l2": { ... },
    "created_at": "2026-04-03T10:00:00Z"
  }
}
```

**Notes**:
- Creates whisper in `whispers_v2` container (no TTL)
- ID format: `{8-char contentGroup}_{lang}` (e.g., `x7k2m9p4_en`)
- Clears `whisperCandidate` flag on source conversation if `conversationId` provided

---

## Data Model

### WhisperItem (Primary Storage — `whispers_v2`)

```typescript
interface WhisperItem {
  id: string                    // "{contentGroup}_{lang}" e.g. "x7k2m9p4_en"
  contentGroup: string          // 8-char short ID
  lang: string                  // language code
  userId: string                // partition key
  
  // L0 Dot
  dot: {
    hook: string                // ≤10 chars
    category: 'whisper'
    color_hint: 'amber'
  }
  
  // L1 Card
  l1: {
    title: string
    summary: string
    participants: 'user+eir'
    via: ['OpenClaw']
  }
  
  // L2 Depth
  l2: {
    content: string
    tension: string
    unresolved: string
    thinking_path: string[]
    eir_role: 'challenger' | 'extender' | 'mirror' | 'catalyst'
    related_topics?: string[]
  }
  
  // Metadata
  conversationId?: string
  conversation_excerpt?: {
    messages: { role: 'user' | 'assistant'; content: string }[]
    total_messages: number
  }
  source: 'openclaw'
  visibility: 'private'
  date: string                  // YYYY-MM-DD
  created_at: string            // ISO 8601
  updated_at: string            // ISO 8601
  ttl: -1                       // no expiration
}
```

---

## Cosmos DB Containers

```
Container: whispers_v2
  Partition Key: /userId
  TTL: -1 (no expiration)

Container: short_ids
  Partition Key: /id
  TTL: -1 (permanent, ensures IDs are never reused)
```

---

## Authentication

All endpoints require `Authorization: Bearer {api_key}` where `api_key` is the OpenClaw pairing key.

The API key is obtained via `POST /oc/connect` with a pairing code, then stored in the skill's config.

---

## Workflow

```
┌─────────────────────────────────────────────────────────────┐
│              Whisper Extraction Workflow                    │
├─────────────────────────────────────────────────────────────┤
│  1. GET /oc/conversations?whisper_candidates=true           │
│     ← Get conversations flagged as whisper candidates       │
│                                                             │
│  2. For each candidate:                                     │
│     GET /oc/conversations/{id}                              │
│     ← Fetch full messages                                   │
│                                                             │
│  3. LLM Analysis                                            │
│     → Analyze conversation for whisper-worthiness           │
│     → Generate dot/l1/l2 structure                          │
│                                                             │
│  4. POST /oc/whispers                                       │
│     → Create whisper                                        │
│     → Server clears candidate flag on conversation          │
└─────────────────────────────────────────────────────────────┘
```

---

*Document Version: 2026-04-04*
*Corresponds to F18-Whisper.md PRD*
