# Eir API Reference

> **Base URL**: Configure via `EIR_API_URL` environment variable. All endpoints are under `/api/oc/`.

## Concepts: Language Settings

| Field | Purpose | Example |
|-------|---------|---------|
| `locale` | UI language (interface, dates, button labels) | `"zh"` or `"en"` |
| `primary_language` | Content production language (interest labels, article summaries) | `"zh"` or `"en"` |
| `bilingual` | Whether to generate both language versions | `true` / `false` |

**Rules**:
- `primary_language` defaults to `locale` if not set
- Interest extraction uses `primary_language`
- Content generation uses `primary_language`, then translates if `bilingual=true`
- Locale affects UI only (not content)

---

## Interest Management APIs

### GET /oc/interests/context

Returns current interests + behavior data for Agent to make sync decisions.

**Response**:
```json
{
  "user": {
    "id": "u_xxx",
    "locale": "zh",
    "primary_language": "zh",
    "bilingual": false
  },
  "topics": [
    {
      "slug": "ai-agents",
      "label": "AI Agents",
      "strength": 0.8,
      "heat": 45,
      "decay_type": "ongoing",
      "engagement": {
        "rate_7d": 0.7,
        "clicks_7d": 4,
        "pushes_7d": 5,
        "trend": "stable"
      },
      "last_pushed_at": "2026-04-02T10:00:00Z",
      "last_engaged_at": "2026-04-02T15:30:00Z",
      "sources": ["conversation", "user_explicit"],
      "first_seen_at": "2026-03-15T08:00:00Z"
    }
  ],
  "groups": [
    {
      "name": "AI & Machine Learning",
      "label": "AI & Machine Learning",
      "description": "Building AI Agent products, focused on architecture decisions and safety patterns",
      "inferredNeeds": ["MCP integration", "safety patterns"],
      "topics": ["ai-agents", "llm-reasoning", "mcp-protocol"],
      "strength": 0.75,
      "heat": 60
    }
  ],
  "behavior_summary": {
    "period_days": 7,
    "total_pushed": 15,
    "total_clicks": 8,
    "total_views_30s": 6,
    "total_skips": 4,
    "engagement_health": 0.85,
    "by_topic": {
      "ai-agents": { "pushed": 5, "clicks": 4, "skips": 1 },
      "rust-programming": { "pushed": 3, "clicks": 0, "skips": 3 }
    }
  },
  "suggestions": [
    {
      "slug": "rust-programming",
      "action": "demote",
      "reason": "0 clicks in 7 days, 100% skip rate"
    },
    {
      "slug": "react-hooks",
      "action": "merge",
      "with": "react",
      "reason": "Overlapping domain, low individual signal"
    }
  ],
  "dismissed": ["crypto", "nft"]
}
```

**Topic fields** (from user interest profile — no dictionary join):

| Field | Description |
|-------|-------------|
| `slug` | Topic identifier |
| `label` | Display label |
| `strength` | Topic strength (0-1) |
| `heat` | Recent activity score |
| `decay_type` | `event` / `ongoing` / `evergreen` |
| `engagement` | 7d click/push stats |
| `sources` | How the topic was discovered |

> Note: `description`, `keywords`, `search_hints` are NOT returned here. They appear in `GET /oc/curation` directives (joined from global dictionary).

**Topic Metadata Sources** (priority order):

| Field | Purpose |
|-------|---------|
| `description` | User's personalized context for this interest area |
| `inferredNeeds` | What the user might want from content in this area |

### POST /oc/interests/sync

Execute interest operations (add/merge/delete/boost/demote).

**Request**:
```json
{
  "operations": [
    {
      "op": "add",
      "slug": "mcp-protocol",
      "label": "MCP Protocol",
      "decay_type": "event",
      "reason": "User discussed MCP 2.0 release with strong interest"
    },
    {
      "op": "merge",
      "from": ["react-hooks", "react-state"],
      "to": "react",
      "to_label": "React",
      "reason": "Same conceptual area"
    },
    {
      "op": "delete",
      "slug": "rust-programming",
      "reason": "System suggested demote, confirmed by skip pattern"
    },
    {
      "op": "boost",
      "slug": "ai-agents",
      "reason": "User explicitly asked to track this topic"
    },
    {
      "op": "demote",
      "slug": "web-development",
      "reason": "Low engagement, shift to explore tier"
    }
  ]
}
```

**Operation Types**:

| Op | Effect | Required Fields |
|----|--------|-----------------|
| `add` | Create new topic with initial strength=0.3 | `slug`, `label`, `decay_type` |
| `merge` | Combine topics, keep highest strength | `from[]`, `to`, `to_label` |
| `delete` | Mark topic as dismissed | `slug` |
| `boost` | Increase strength by 0.2 (user explicit) | `slug` |
| `demote` | Decrease strength by 0.2, change tier | `slug` |

**decay_type Values**:

| Type | Meaning | Decay Rate |
|------|---------|------------|
| `event` | Time-sensitive news (GPT-5 launch) | Fast: 70% at 7d, 30% at 14d |
| `ongoing` | Active interest (AI safety) | Slow: 95% at 7d, 85% at 30d |
| `evergreen` | Fundamental interest (productivity) | Minimal: 98% at 7d, 90% at 60d |

**Response**:
```json
{
  "ok": true,
  "applied": 5,
  "results": [
    { "op": "add", "slug": "mcp-protocol", "status": "created" },
    { "op": "merge", "from": ["react-hooks", "react-state"], "to": "react", "status": "merged" },
    { "op": "delete", "slug": "rust-programming", "status": "dismissed" },
    { "op": "boost", "slug": "ai-agents", "status": "boosted", "new_strength": 0.9 },
    { "op": "demote", "slug": "web-development", "status": "demoted", "new_strength": 0.5 }
  ],
  "profile_snapshot": {
    "topic_count": 12,
    "top_topics": ["ai-agents", "mcp-protocol", "react"],
    "last_sync": "2026-04-03T07:50:00Z",
    "embedding_updated": true,
    "embedding_meta": {
      "version": 2,
      "model": "EmbeddingGemma-300M",
      "dim": 256,
      "strategy": "group-weighted",
      "groupsUsed": 18,
      "groupsTotal": 23,
      "topicsWithEmbedding": 55,
      "topicsTotal": 70,
      "skippedDimMismatch": 0,
      "skippedNoEmbedding": 15,
      "updatedAt": 1775311200000
    }
  }
}
```

---

## Curation APIs

### GET /oc/curation

Returns curation directives for today's content collection.

**Response**:
```json
{
  "user": {
    "primary_language": "en",
    "bilingual": false
  },
  "schema_version": "2",
  "min_skill_version": "1.0.0",
  "directives": [
    {
      "type": "focus",
      "slug": "ai-agents",
      "topic": "AI Agents",
      "description": "AI agent frameworks and autonomous systems",
      "keywords": ["MCP", "model context protocol"],
      "search_hints": ["AI agent framework", "multi-agent"],
      "strength": 0.8,
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

**Top-level Fields**:

| Field | Description |
|-------|-------------|
| `user` | User language preferences (`primary_language`, `bilingual`) |
| `schema_version` | API response schema version. Agent must check compatibility before proceeding. |
| `min_skill_version` | Minimum skill version required to process this response. |
| `directives` | Array of curation directives with tier, topic metadata, and thresholds |
| `budget` | Suggested item counts and remaining quota |
| `exclude` | Topics/keywords to avoid |

**Directive Metadata Sources**:

| Field | Source | Fallback |
|-------|--------|----------|
| `description` | Global `interest_topics` dictionary | null → pipeline enriches locally |
| `keywords` | Global `interest_topics` dictionary | null → pipeline enriches locally |
| `search_hints` | Global `interest_topics` dictionary | null → pipeline generates from topic |

**Local Enrichment** (when API returns null):

Pipeline runs `interest_extractor.py enrich_topics()` to generate:
- `embedding_text`: Combines topic label + user group description + inferred needs
- `keywords_enriched`: Bilingual keywords from label variations
- `search_queries`: Fallback queries for topics without API hints

This ensures embedding/matching works even for new topics without dictionary entries.

**Tier Logic**:

| Tier | Selection Criteria | Quality Bar |
|------|-------------------|-------------|
| `tracked` | user_explicit source | 0.6 |
| `focus` | strength ≥ 0.7 AND not demoted | 0.7 |
| `explore` | 0.3 ≤ strength < 0.7 OR demoted focus | 0.6 |
| `seed` | strength < 0.3, discovery items | 0.8 |

**Scoring Formula**:

```
score = strength × cooldown_factor × engagement_boost

cooldown_factor:
  - 1.0 if not pushed in 24h
  - 0.3 if pushed recently (cooldown period)

engagement_boost:
  - min(1.5, 0.5 + topic_engagement_rate)
```

**Dispatcher Selection** (v8):

1. Sort by composite score: `(needs_generate, push_penalty, priority, freshness, relevance)`
2. `push_penalty`: Based on 3-day push frequency (avoid repetition)
3. Diversity enforcement: If all top-N are same type, swap weakest for different type
4. Cooldown: 36h between pushes for same topic

### POST /oc/content

Push generated content to Eir.

**Request**:
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
        "title": "MCP Protocol v2.0: Infrastructure for Multi-Model Collaboration",
        "summary": "Anthropic releases MCP 2.0...",
        "bullets": ["Multi-model context sharing", "Four-tier permission system"],
        "via": ["Anthropic Blog", "The Verge"]
      },
      "l2": {
        "content": "...(500+ words)...",
        "bullets": [{ "text": "...", "confidence": "high" }],
        "context": "...",
        "eir_take": "..."
      },
      "sources": [
        { "url": "https://...", "title": "...", "name": "Anthropic Blog" }
      ]
    }
  ]
}
```

**Key fields**:
- `lang` (required): Language code ("en", "zh"). Each language version is a separate document.
- `l1`, `l2` are **top-level** per item (NOT nested in `locales{}`).
- For bilingual content, push two separate items with the same `slug`/`topicSlug` but different `lang`.
- `locales{}` format is still accepted for backward compatibility but deprecated.
- `l1.via`: auto-derived from `sources[].name` by pipeline; API also falls back if empty.

> **Field types, limits, and validation rules** → see `references/content-spec.md`.

**Response:**
```json
{
  "accepted": 1,
  "rejected": 0,
  "results": [
    {
      "status": "accepted",
      "id": "a3k9m2x7_en",
      "contentGroup": "a3k9m2x7",
      "slug": "mcp-protocol-2-0",
      "langs": ["en"]
    }
  ]
}
```

**ID Format**: `{8-char contentGroup}_{lang}` (e.g., `a3k9m2x7_en`).

- `contentGroup`: 8-char base64url, globally unique, registered in `short_ids` container.
- All language versions of the same article share the same `contentGroup`.

Possible `status` values: `accepted`, `skipped` (duplicate source_url), `error`.

---

## Sync Workflow

```
┌─────────────────────────────────────────────────────────────────┐
│                    Daily Interest Sync                          │
├─────────────────────────────────────────────────────────────────┤
│  1. GET /oc/interests/context                                   │
│     ← Get topics (with metadata), groups (with description),    │
│       behavior data, suggestions                                │
│                                                                 │
│  2. Agent analyzes conversations (uses primary_language)        │
│     → Extracts new interests                                    │
│     → Reviews system suggestions                                │
│     → Decides: add / merge / delete / boost / demote            │
│                                                                 │
│  3. POST /oc/interests/sync                                     │
│     → Send operations (not strength/heat calculations)          │
│     ← Server applies ops, recalculates metrics                  │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                    Content Curation                             │
├─────────────────────────────────────────────────────────────────┤
│  1. GET /oc/curation                                            │
│     ← Get curation directives with engagement-aware tiers       │
│     ← Includes description/keywords from global dictionary      │
│                                                                 │
│  2. Pipeline enrichment (if API returns null)                   │
│     → interest_extractor.py enrich_topics()                     │
│     → Combines: topic labels + group descriptions + needs       │
│     → Generates: embedding_text, keywords, fallback queries     │
│                                                                 │
│  3. Topic matching (embeddings)                                 │
│     → Uses enriched embedding_text (not just slug)              │
│     → Threshold: 0.52 (reduced noise vs 0.45)                   │
│                                                                 │
│  4. Content generation                                          │
│     → Uses quality_threshold to filter                          │
│     → Uses search_hints or fallback queries                     │
│                                                                 │
│  5. Dispatcher selection                                        │
│     → Composite scoring with push_penalty + freshness           │
│     → 36h cooldown between same-topic pushes                    │
│     → Diversity enforcement across types                        │
│                                                                 │
│  6. POST /oc/content                                            │
│     → Push generated items (each lang as separate item)          │
│     → For bilingual: push 2 items with same slug, different lang │
│     → Optionally use PATCH /oc/content/:id/locale/:lang          │
└─────────────────────────────────────────────────────────────────┘
```

---

## Public Content API

Public content uses the same `content_items_v2` container and schema as private content, differentiated by `visibility` and `channelId`.

| | Private | Public |
|---|---|---|
| Container | `content_items_v2` | `content_items_v2` (same) |
| userId (PK) | `u_xxx` | `public:{channelId}` |
| visibility | `private` | `public` |
| channelId | `user-private` | `eir-express`, etc |
| TTL | 30 days | 3 days |

**Channel** = a content stream from a provider. One provider can have multiple channels (e.g. `eir-express`, `eir-deep`). Channel ID uses provider prefix for global uniqueness.

### POST /pc/content

Push public content. Requires admin auth.

**Query param or body field**: `channelId` (required, e.g. `eir-express`)

**Request**: Same `{items: [...]}` format as `POST /oc/content`.

Additional optional fields per item:
- `qualityScore` (number, 0-1, default 0.5)
- `freshness` (string: `"breaking"` | `"daily"` | `"evergreen"`, default `"daily"`)
- `categories` (string[], coarse categories e.g. `["ai", "tech"]`)

**Response**: Same format as `POST /oc/content`.

### GET /pc/content

List public content. Requires admin auth.

**Query params**:
- `channelId` — filter by channel (single-partition read, fast)
- `limit` — max results (default 20, max 100)

If `channelId` omitted, returns all public content (cross-partition, slower).

---

## Whisper APIs

### GET /oc/conversations

List user conversations with optional filtering.

**Query Parameters**:

| Param | Type | Description |
|-------|------|-------------|
| `limit` | int | Max results (default 20, max 50) |
| `whisper_candidates` | bool | Filter to conversations marked as whisper candidates |
| `since` | ISO 8601 | Filter to conversations started after this time |

**Response**:
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

### GET /oc/conversations/:id

Get full conversation with all messages.

**Response**:
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

### POST /oc/whispers

Create a single whisper from extracted conversation insight.

**Request**:
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

**Response**:
```json
{
  "ok": true,
  "id": "whisper_u_xxx_1712345678_abcd",
  "whisper": { ... }
}
```

**Notes**:
- Creates whisper in `whispers` container and syncs to `content_items` for display
- Clears `whisperCandidate` flag on source conversation if `conversationId` provided

---

## Connection & Profile APIs

### POST /oc/connect

Register with a pairing code. No API key needed (this is how you get one).

**Request:**
```json
{ "code": "ABCD-1234" }
```

**Response:**
```json
{ "apiKey": "eir_oc_xxx", "userId": "u_abc123", "status": "connected" }
```

App-level vs user-level is determined by the pairing code origin (admin panel vs user settings), not exposed in the response. Use `userId` and `apiKey` for all subsequent calls.

### DELETE /oc/connect

Disconnect OpenClaw from user account. Revokes the API key.

**Response:**
```json
{ "status": "disconnected" }
```

### POST /oc/refresh-key

Rotate API key without re-pairing. Old key stays valid for 60s grace period.

**Response:**
```json
{ "apiKey": "eir_oc_new_xxx", "rotatedAt": "2026-04-03T07:50:00Z", "prevKeyExpiresAt": 1712345678000 }
```

### POST /oc/profile

Update user interests via signals, long-term interests, or profile context.

**Request:**
```json
{
  "signals": [
    { "slug": "mcp-protocol", "label": "MCP", "strength": 0.7, "source": "conversation" }
  ],
  "long_term_interests": ["AI agents", "developer tools"],
  "profile_update": "Building an AI content product"
}
```

All fields optional. `signals` merges into interest profile topics. `long_term_interests` saves to user doc. `profile_update` saves as profile context.

### GET /oc/context

**(Deprecated)** — Use `GET /oc/interests/context` for interest data. User preferences are available in `GET /oc/curation` response.

User curation context snapshot (daily sync). Returns interests, preferences, and push limits.

**Response:**
```json
{
  "interests": {
    "topics": { "ai-agents": { "strength": 0.8, "heat": 45 } },
    "groups": [...],
    "userEmbedding": [0.12, -0.34, ...],
    "embeddingMeta": {
      "version": 2, "model": "EmbeddingGemma-300M", "dim": 256,
      "topicsUsed": 8, "topicsTotal": 12, "updatedAt": 1775311200000
    }
  },
  "preferences": {
    "locale": "zh",
    "bilingual": false,
    "contentPrefs": {}
  },
  "limits": {
    "daily_max": 8,
    "pushed_today": 3,
    "remaining": 5
  },
  "content_prompt": "..."
}
```

### GET /oc/sources

Returns already-pushed source URLs for dedup. Pipeline uses this to avoid re-crawling.

**Query params:** `?days=7` (default: 7 days lookback)

**Response:**
```json
{ "urls": ["https://anthropic.com/...", "https://arxiv.org/..."], "count": 12, "since": "2026-03-28T00:00:00Z" }
```

---

## Content Read/Write APIs

### GET /oc/content/:id

Read back a single content item.

**Response:**
```json
{
  "id": "a3k9m2x7_en",
  "contentGroup": "a3k9m2x7",
  "lang": "en",
  "slug": "anthropic-trust-tiers",
  "topicSlug": "ai-agents",
  "dot": {},
  "l1": {},
  "l2": {},
  "sources": [...],
  "created_at": "2026-04-03T10:00:00Z",
  "updated_at": "2026-04-03T12:00:00Z"
}
```

### PATCH /oc/content/:id/locale/:lang

Add or update a language version. This creates or updates the `{contentGroup}_{lang}` document directly.

**Request:**
```json
{
  "l1": { "title": "Translated Title", "summary": "..." },
  "l2": { "content": "...", "bullets": [...] }
}
```

**Response:**
```json
{ "ok": true, "available_langs": ["en", "zh"] }
```

---

## Server-Side Calculations

**What the Agent does NOT calculate**:
- `strength` — computed from signals + decay
- `heat` — computed from recent behavior
- `engagement_health` — computed from click rates
- `score` — computed from strength × cooldown × engagement

**What the Agent provides**:
- `decay_type` — event / ongoing / evergreen
- `label` — in user's primary_language
- `reason` — for logging and audit

---

## Data Architecture

### Cosmos DB Containers

| Container | Partition Key | Purpose | TTL |
|-----------|---------------|---------|-----|
| `content_items_v2` | `/userId` | Content (private: `u_xxx`, public: `public:{channelId}`) | private 30d, public 3d |
| `content_operations` | `/id` | Content ops: topic stats, pipeline metrics | — |
| `whispers_v2` | `/userId` | Whisper items | - |
| `shared_content_v2` | `/id` | Shared content snapshots | - |
| `short_ids` | `/id` | ID registry (uniqueness) | - |
| `id_mapping` | `/id` | Old→new ID mapping | 90d |

### Content ID Format

```
{contentGroup}_{lang}     e.g. a3k9m2x7_en
```

- `contentGroup`: 8-char base64url, globally unique
- `lang`: language code (en, zh)
- Each language version is an independent document
- All language versions share the same `contentGroup`

### Global vs Personal Data

| Data | Scope | Contains |
|------|-------|----------|
| `interest_topics` | Global dictionary | Universal definitions: labels, description (generic), keywords |
| `user_interests.topics` | Per-user | Strength, heat, sources, engagement history |
| `user_interests.groups` | Per-user | **Personalized** description, inferredNeeds |
| `user_interests.userEmbedding` | Per-user | 256d vector, weighted mean of topic embeddings |
| `user_interests.embeddingMeta` | Per-user | version, model, dim, topicsUsed, skipped counts |

### Embedding Model

> ⚠️ **All embeddings in this system use the same model and dimension. Do not mix.**

| Property | Value |
|----------|-------|
| Model | **EmbeddingGemma-300M** (Google DeepMind, 300M params) |
| HuggingFace | `google/embeddinggemma-300m` |
| Native dimension | 768d |
| Storage dimension | **256d** (Matryoshka truncation) |
| Normalization | L2 unit vectors |
| Previous model | e5-small (384d), migrated 2026-03-29 |

**Where embeddings are stored:**
- `interest_topics.embedding` — 256d per topic (203 topics, all populated)
- `user_interests.userEmbedding` — 256d per user (group-weighted mean of topics)
- Pipeline local cache — `.npz` files for search/article embeddings

**Consistency rule**: If the model changes, bump `EMBEDDING_VERSION` in `api/index.ts`. The server validates `embedding.length === EMBEDDING_DIM` and skips mismatched vectors during user embedding computation.

### Embedding Text Construction

For topic matching, build embedding text from:

1. **Topic label** (bilingual if available)
2. **Group description** (from user's interestGroups — personalized)
3. **Group inferredNeeds** (from user's interestGroups)
4. **Global description** (fallback from interest_topics dictionary)

This ensures:
- New users get generic matching from global dictionary
- Active users get personalized matching from their groups
- Pipeline `enrich_topics()` handles missing data locally

### User Embedding

The server computes `userEmbedding` at the **interest group level**, not flat topic level. This reduces noise from low-engagement FRE-seeded topics.

**When it's recomputed:**
- After `POST /oc/interests/sync` (OC agent updates interests)
- After `POST /oc/interests/extract` (conversation interest extraction)
- After `POST /interests/fre` (first-run experience onboarding)

**Algorithm (group-weighted):**
1. Build group → topic slug mapping from `interestGroups`
2. Ungrouped active topics become singleton "groups"
3. Batch-load all needed topic embeddings from `interest_topics` dictionary
4. For each group:
   - Group embedding = **mean** of its topics' embeddings
   - Group weight = `max(topic.strength)` × interaction multiplier:
     - **Interacted** (sources include user_explicit / eir_chat / openclaw / explore_click): `1.0×`
     - **FRE-only** (only fre_selection, no interaction): `0.3×`
5. Skip groups where no topic has a valid embedding
6. User embedding = **weighted mean** of group embeddings, L2 normalized

**Dimension validation**: skip topics with `embedding.length ≠ EMBEDDING_DIM` (256)

**Fallback rules:**
- If some groups lack embeddings → compute with available ones
- If ALL groups lack embeddings → keep existing `userEmbedding` unchanged
- If model/dim changes → old-dim embeddings skipped, new ones used when available

**Example** (admin profile):
```
22 groups used / 29 total
63 topics with embedding / 80 total
Interacted weight: 9.75 (81.1%)
FRE-only weight:   2.26 (18.9%)
```

**Stored fields:**
```json
{
  "userEmbedding": [0.12, -0.34, ...],
  "embeddingMeta": {
    "version": 2,
    "model": "EmbeddingGemma-300M",
    "dim": 256,
    "strategy": "group-weighted",
    "groupsUsed": 22,
    "groupsTotal": 29,
    "topicsWithEmbedding": 63,
    "topicsTotal": 80,
    "skippedDimMismatch": 0,
    "skippedNoEmbedding": 17,
    "updatedAt": 1775311200000
  },
  "embeddingUpdatedAt": 1775311200000
}
```

**Constants** (in `api/index.ts`):
```typescript
const EMBEDDING_MODEL = 'EmbeddingGemma-300M'
const EMBEDDING_DIM = 256
const EMBEDDING_VERSION = 2
```

---

## Embedding Contract

> **Single source of truth for all embedding data in this system.**

Every embedding — whether for topics, users, or content — MUST use the same model and dimension.

### Accepted Embedding Format

When sending embeddings to any API endpoint, use the structured format:

```json
{
  "embedding": {
    "vector": [0.12, -0.34, ...],
    "model": "EmbeddingGemma-300M",
    "dim": 256
  }
}
```

Legacy format (raw array) is also accepted where noted — the server validates dimension:

```json
{
  "embedding": [0.12, -0.34, ...]   // Must be exactly 256d
}
```

**Not sending an embedding is always valid.** The server computes user embeddings from the topic dictionary.

### Validation Rules (Server-Enforced)

| Check | Behavior on Mismatch |
|-------|---------------------|
| `model !== 'EmbeddingGemma-300M'` | **Reject** (400 error) |
| `dim !== 256` | **Reject** (400 error) |
| `vector.length !== 256` | **Reject** (400 error) |
| `vector` contains NaN/Infinity | **Reject** (400 error) |
| `embedding` field omitted/null | **Accept** (no embedding stored) |

### Where Validation Applies

| Endpoint | Embedding Source | Validation |
|----------|-----------------|------------|
| `POST /oc/content` | Pipeline embeds article text | ✅ model/dim enforced |
| `POST /pc/content` | Pipeline embeds article text | ✅ model/dim enforced |
| `POST /admin/interest-topics/backfill` | Pipeline embeds topic text | ✅ dim enforced (legacy + structured) |
| `POST /oc/interests/sync` | N/A — server computes from dictionary | N/A (no embedding input) |
| `POST /oc/interests/extract` | N/A — server computes from dictionary | N/A (no embedding input) |
| `POST /interests/fre` | N/A — server computes from dictionary | N/A (no embedding input) |

### Storage Schema

**Content items** (when embedding is provided):
```json
{
  "embedding": [0.12, -0.34, ...],
  "embeddingModel": "EmbeddingGemma-300M",
  "embeddingDim": 256
}
```

**Interest topics** (dictionary):
```json
{
  "embedding": [0.12, -0.34, ...],
  "embDim": 256,
  "embeddingAt": 1774827625822
}
```

**User profile** (computed by server):
```json
{
  "userEmbedding": [0.12, -0.34, ...],
  "embeddingMeta": { "version": 2, "model": "EmbeddingGemma-300M", "dim": 256, "strategy": "group-weighted", ... }
}
```

---

## Interest Extraction → Sync Data Flow

Complete data flow for how user interests are discovered, synced, and turned into embeddings.

### Step 1: Extract Interests from Conversations

**Who**: Eir agent (LLM)
**When**: After each user conversation or periodically
**How**: Analyze conversation content using interest extraction prompt

**Input needed from server** (`GET /oc/interests/context`):
```json
{
  "topics": {
    "ai-agents": { "strength": 0.8, "heat": 0.6, "sources": ["eir_chat"], "label": "AI Agents" },
    "react": { "strength": 0.5, "heat": 0.2, "sources": ["fre_selection"], "label": "React" }
  },
  "interestGroups": [...],
  "suggestions": [
    { "type": "demote", "slug": "web-development", "reason": "Low engagement 14d" }
  ]
}
```

**Agent outputs**: A list of operations (see Step 2).

### Step 2: Sync Operations to Server

**Who**: Eir agent calls `POST /oc/interests/sync`
**What agent sends**:

```json
{
  "operations": [
    {
      "op": "add",
      "slug": "mcp-protocol",
      "label": "MCP Protocol",
      "labelZh": "MCP 协议",
      "decay_type": "event",
      "reason": "User discussed MCP 2.0 release"
    },
    {
      "op": "boost",
      "slug": "ai-agents",
      "reason": "Continued deep discussion"
    },
    {
      "op": "demote",
      "slug": "web-development",
      "reason": "Confirmed system suggestion — no engagement"
    }
  ]
}
```

**What agent does NOT send**:
- ❌ Embeddings (server computes from topic dictionary)
- ❌ Strength values (server calculates based on operation type)
- ❌ Heat values (server calculates from engagement data)

### Step 3: Server Processes Operations

For each operation:
1. Apply to `profile.topics` (add/merge/delete/boost/demote)
2. Update `lastUpdatedAt`
3. **Recompute user embedding** (group-weighted algorithm):
   - Looks up each topic's embedding from `interest_topics` dictionary
   - Groups topics by `interestGroups`, computes group-level weighted mean
   - L2 normalizes the result
4. Returns response with `embedding_updated: true/false` + `embedding_meta`

### Step 4: Embedding Propagation

After sync, the updated `userEmbedding` is used by:
- **Content recommendation**: cosine similarity between `userEmbedding` and `content.embedding`
- **Curation directives**: `GET /oc/curation` uses embedding to rank focus topics
- **Search dedup**: Pipeline uses embedding distance to avoid duplicate content

### What the Agent Needs to Know

| Concern | Answer |
|---------|--------|
| Do I compute embeddings? | **No.** Server handles all embedding computation. |
| Do I send embeddings with interest sync? | **No.** Just send operations (add/boost/merge/etc). |
| What model is used? | **EmbeddingGemma-300M**, 256d Matryoshka. You don't need to know this for interest sync. |
| When do I send embeddings? | **Only with content** (`POST /oc/content`, `POST /pc/content`). Pipeline embeds article text before pushing. |
| What if a topic I add has no embedding in the dictionary? | Server skips it for embedding computation. The topic still works for keyword/category matching. |
| What format for content embeddings? | `{ vector: [...], model: 'EmbeddingGemma-300M', dim: 256 }` or raw `number[256]`. |
