# Eir API Reference

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
      "label": "AI 智能体",
      "labels": { "zh": ["AI 智能体"], "en": ["AI agents"] },
      "description": "...",
      "keywords": ["agent", "autonomous"],
      "search_hints": ["AI agent framework"],
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
      "name": "AI & 机器学习",
      "label": "AI & 机器学习",
      "description": "我在构建 AI Agent 产品，关注架构决策和安全模式",
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

**Topic Metadata Sources** (priority order):

| Field | Source | Fallback |
|-------|--------|----------|
| `description` | Global `interest_topics` dictionary | null |
| `keywords` | Global `interest_topics` dictionary | [] |
| `search_hints` | Global `interest_topics` dictionary | [] |

**Group Fields** (personalized):

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
      "label": "MCP 协议",
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
    "last_sync": "2026-04-03T07:50:00Z"
  }
}
```

---

## Curation APIs

### GET /oc/content

Returns curation directives for today's content collection.

**Response**:
```json
{
  "tracked": [
    {
      "type": "track",
      "slug": "mcp-protocol",
      "topic": "MCP 协议",
      "description": "Model Context Protocol for AI agents",
      "keywords": ["MCP", "model context protocol"],
      "search_hints": ["MCP 2.0", "Anthropic MCP"],
      "strength": 0.9,
      "engagement_health": 1.1,
      "priority": "high",
      "max_items": null,
      "quality_threshold": 0.6,
      "freshness": "24h"
    }
  ],
  "directives": [
    {
      "type": "focus",
      "slug": "ai-agents",
      "topic": "AI 智能体",
      "description": "AI agent frameworks and autonomous systems",
      "keywords": ["agent", "autonomous", "LLM"],
      "search_hints": ["AI agent framework", "multi-agent"],
      "strength": 0.8,
      "score": 0.85,
      "engagement_health": 0.9,
      "quality_threshold": 0.7,
      "freshness": "7d"
    },
    {
      "type": "explore",
      "slug": "rust-programming",
      "topic": "Rust",
      "strength": 0.75,
      "score": 0.45,
      "engagement_health": 0.4,
      "quality_threshold": 0.6,
      "note": "Demoted from focus due to low engagement"
    },
    {
      "type": "seed",
      "slug": "spatial-computing",
      "topic": "空间计算",
      "strength": 0.2,
      "score": 0.18,
      "quality_threshold": 0.8,
      "note": "Discovery item"
    }
  ],
  "engagement_summary": {
    "overall_health": 0.85,
    "trend": "stable",
    "recent_rate": 0.53,
    "recommendation": "maintain_current_mix"
  },
  "budget": {
    "suggested_total": 6,
    "tracked_allowance": "unlimited",
    "focus_allowance": 3,
    "explore_allowance": 2,
    "seed_allowance": 1
  },
  "content_prompt": "...",
  "exclude": {
    "disliked": ["crypto", "nft"]
  },
  "refresh_interval_hours": 4
}
```

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
      "source_lang": "en",
      "dot": {
        "hook": "MCP 2.0 发布",
        "category": "focus",
        "color_hint": "blue"
      },
      "l1": {
        "title": "MCP 协议 v2.0：多模型协同的基础设施",
        "summary": "Anthropic 发布 MCP 2.0...",
        "bullets": ["多模型上下文共享", "四级权限系统"],
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
│  1. GET /oc/content                                             │
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
│     → Push generated items (in primary_language)                │
│     ← If bilingual, PATCH /oc/content/:id/locale/:lang          │
└─────────────────────────────────────────────────────────────────┘
```

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
{ "apiKey": "eir_oc_new_xxx", "prevKeyExpiresAt": 1712345678000 }
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

User curation context snapshot (daily sync). Returns interests, preferences, and push limits.

**Response:**
```json
{
  "interests": {
    "topics": { "ai-agents": { "strength": 0.8, "heat": 45 } },
    "groups": [...],
    "userEmbedding": [0.12, -0.34, ...]
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
  "id": "ci_u_abc123_1711234567_x3k2",
  "slug": "anthropic-trust-tiers",
  "topicSlug": "ai-agents",
  "source_lang": "en",
  "available_langs": ["en", "zh"],
  "locales": { "en": { "l1": {}, "l2": {} }, "zh": { "l1": {}, "l2": {} } },
  "dot": {},
  "sources": [...],
  "content_url": "https://www.heyeir.com/en/content/anthropic-trust-tiers-x3k2",
  "createdAt": "2026-04-03T10:00:00Z",
  "updated_at": "2026-04-03T12:00:00Z"
}
```

### PATCH /oc/content/:id/locale/:lang

Add or update a language version. Deep merges l1/l2 with existing data.

**Request:**
```json
{
  "l1": { "title": "中文标题", "summary": "..." },
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

### Global vs Personal Data

| Data | Scope | Contains |
|------|-------|----------|
| `interest_topics` | Global dictionary | Universal definitions: labels, description (generic), keywords |
| `user_interests.topics` | Per-user | Strength, heat, sources, engagement history |
| `user_interests.groups` | Per-user | **Personalized** description, inferredNeeds |

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
