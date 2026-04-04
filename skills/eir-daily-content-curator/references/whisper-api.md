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
  "id": "whisper_u_xxx_1712345678_abcd",
  "whisper": {
    "id": "whisper_u_xxx_1712345678_abcd",
    "userId": "u_xxx",
    "type": "whisper",
    "dot": { "hook": "...", "category": "whisper", "color_hint": "amber" },
    "l1": { ... },
    "l2": { ... },
    "createdAt": 1712345678000
  }
}
```

**Notes**:
- Creates whisper in `whispers` container (no TTL)
- Syncs to `content_items` for Z0/Z1/Z2 display
- Clears `whisperCandidate` flag on source conversation if `conversationId` provided

---

## Data Model

### WhisperItem (Primary Storage)

```typescript
interface WhisperItem {
  id: string                    // "whisper_{userId}_{timestamp}_{rand}"
  userId: string                // partition key
  type: 'whisper'
  
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
  createdAt: number
  updatedAt: number
}
```

### content_items Sync

Whispers are also written to `content_items` for feed display:

```typescript
{
  id: string,                    // same as whisper.id
  userId: string,
  type: 'whisper',
  dot: { hook, category: 'whisper', color_hint: 'amber' },
  l1: { title, summary, via: ['OpenClaw'] },
  l2: { ... },
  date: string,                  // YYYY-MM-DD
  createdAt: string,             // ISO 8601
  publish_time: string,          // ISO 8601
  position: { x, y },
  ttl: -1,                       // no TTL
}
```

---

## Cosmos DB Containers

```
Container: whispers
  Partition Key: /userId
  TTL: -1 (no expiration)

Container: content_items (existing, reused)
  Type 'whisper' records added for display
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
