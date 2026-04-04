# Eir Interest System Rules

This document explains how Eir calculates interest strength, engagement health, and makes curation decisions.

## Architecture: Separation of Concerns

| Responsibility | Who | Why |
|----------------|-----|-----|
| **New interest discovery** | Agent (LLM) | Understands conversation context |
| **Interest merging** | Agent (LLM) | Requires semantic understanding |
| **Setting decay_type** | Agent (LLM) | Judges if event vs ongoing |
| **Calculating strength/heat** | Eir Server | Has complete behavior data |
| **Applying decay** | Eir Server | Runs daily, deterministic |
| **Generating suggestions** | Eir Server | Analyzes engagement patterns |

## Language Settings

| Setting | Purpose | Example |
|---------|---------|---------|
| `locale` | UI language (buttons, dates) | `"zh"` |
| `primary_language` | Content production language | `"zh"` |
| `bilingual` | Generate both language versions | `true/false` |

**Interest labels** always use `primary_language`, NOT `locale`.

## Core Philosophy

**Quality over quantity.** If there are 10 high-quality articles matching user interests today, push all 10. If only 2 are worth reading, push only 2. The goal is to respect the user's attention, not fill a quota.

**Engagement drives adaptation.** When users stop engaging with topics they used to like, their interests have likely shifted. Decay those topics faster and explore new territory.

## Core Metrics (Server-Calculated)

### Strength (长期兴趣强度)

**What it represents**: How much the user cares about this topic over time.

**Range**: 0.0 - 1.0

**Base calculation** (server-side):
```
strength = min(1.0, base_strength + (occurrences * 0.05))
```

**Dynamic decay**: Strength decays based on `decay_type` (set by Agent).

| decay_type | Decay Behavior |
|------------|----------------|
| **event** (e.g., "GPT-5 launch") | Fast: 70% at 7d, 30% at 14d |
| **ongoing** (e.g., "AI safety") | Slow: 95% at 7d, 85% at 30d |
| **evergreen** (e.g., "productivity") | Minimal: 98% at 7d, 90% at 60d |

### Engagement Health (参与度健康值)

**What it represents**: Is the user still interested in topics we're pushing?

**Calculation** (server-side):
```
engagement_rate = (clicks + views_30s+) / items_pushed (last 7 days)
engagement_health = engagement_rate / baseline_rate

baseline_rate = user's average engagement rate over 30 days
```

**Thresholds**:
| Health | Meaning | Action |
|--------|---------|--------|
| > 1.2 | User is more engaged than usual | Increase content volume |
| 0.8 - 1.2 | Normal engagement | Maintain current balance |
| 0.5 - 0.8 | Declining engagement | Add more explore content |
| < 0.5 | User interests may have shifted | Pause focus, emphasize explore/seed |

### Heat (短期活跃度)

**What it represents**: Recent activity level for this topic.

**Range**: 0 - 100

```
heat = sum(event_weights) * recency_multiplier

Event weights:
- click: 5
- view (>30s): 3
- view (<30s): 1
- bookmark: 10
- share: 15

recency_multiplier:
- last 24h: 1.0
- 24-48h: 0.5
- 48-72h: 0.25
- 72h+: 0.1
```

## Curation Logic

### Step 1: Determine Daily Budget

NOT a fixed number. Based on:

1. **Content quality available today**: How many items pass the quality threshold?
2. **User engagement health**: If declining, push fewer items
3. **Topic heat**: If topics are "hot" (news-heavy day), allow more items

```
base_budget = 5  // Default target
quality_factor = high_quality_items_available / 10  // Scale by quality
engagement_factor = min(1.5, max(0.5, engagement_health))
today_budget = round(base_budget * quality_factor * engagement_factor)
```

### Step 2: Allocate by Priority

**Priority tiers** (NOT fixed counts):

| Tier | Definition | Selection Logic |
|------|------------|-----------------|
| **tracked** | User explicitly follows | All high-quality content, no cap |
| **focus** | strength ≥ 0.7 AND engagement_health ≥ 0.5 | Select by content quality score |
| **explore** | 0.3 ≤ strength < 0.7 OR (strength ≥ 0.7 AND low engagement) | Random sample from top quality |
| **seed** | strength < 0.3 | 1-2 items to discover new interests |

**Key rule**: If engagement_health < 0.5 for a topic, demote it from "focus" to "explore" regardless of strength.

### Step 3: Content Quality Filter

Each candidate item scored on:

```
quality_score = (
  topic_relevance * 0.25 +   // How well does it match the topic?
  source_authority * 0.25 +  // Trusted source? Original reporting?
  freshness * 0.20 +         // How recent?
  depth * 0.15 +             // Substantial content vs. thin post?
  novelty * 0.15             // Not duplicate/similar to recent items?
)
```

**Minimum threshold**: quality_score ≥ 0.6 to be considered for push

### Step 4: Diversity

- Max 2 items from same interest group (unless all are exceptionally high quality)
- If user has < 5 tracked topics, include 1 seed item to encourage exploration
- If user has > 15 tracked topics, prioritize breadth over depth

### Step 5: Cooldown

**Topic-level cooldown** (not fixed):
- If topic pushed in last 24h AND no new high-quality content: skip
- If topic pushed in last 24h BUT new breaking content: allow

**Source-level cooldown**:
- Same source URL: never repeat
- Same source domain: max 2 per day (unless it's the user's preferred source)

## Interest Signals

### Positive Signals

| Signal | Strength Impact | Notes |
|--------|-----------------|-------|
| Explicit "track this" | +0.5 | User intent is gold |
| Deep discussion (3+ turns) | +0.2 | Shows genuine interest |
| Curious question | +0.1 | "How does X work?" |
| Click on content | +0.05 | Basic engagement |
| View >60s | +0.03 | Actually read it |
| Bookmark | +0.1 | Want to revisit |
| Share | +0.15 | Worth telling others |

### Negative Signals

| Signal | Action |
|--------|--------|
| "Not interested" on content | topic.strength -= 0.3, add to cooldown |
| Skip 3+ items from same topic | Accelerate decay (2x rate) |
| "Don't recommend" | topic.dismissed = true, exclude forever |
| Low engagement rate (<30%) | Demote to explore tier |

## Engagement-Driven Adaptation

### When Engagement Drops

```
if topic.engagement_rate < 0.3 for last 7 days:
  topic.strength *= 0.7  # Accelerated decay
  topic.tier = 'explore'  # Demote from focus
```

### When Engagement Spikes

```
if topic.engagement_rate > 0.8 for last 3 days:
  topic.strength = min(1.0, topic.strength * 1.2)  # Boost
  topic.tier = 'focus'  # Promote if was explore
```

### Interest Lifecycle

```
New interest → Watch (seed) → Growing (explore) → Active (focus) → Declining (explore) → Dormant (seed) → Dropped
```

Each stage transition based on engagement, not time. A topic can stay in "focus" for years if user keeps engaging.

## API: Curation Directives

`GET /oc/content` returns:

```json
{
  "tracked": [
    {
      "slug": "mcp-protocol",
      "topic": "MCP Protocol",
      "strength": 0.9,
      "engagement_health": 1.1,
      "priority": "high",
      "max_items": null,  // No cap for tracked
      "freshness": "24h",
      "keywords": ["MCP", "model context protocol"],
      "search_hints": ["MCP 2.0", "Anthropic MCP"]
    }
  ],
  "directives": [
    {
      "type": "focus",
      "slug": "ai-agents",
      "topic": "AI Agents",
      "strength": 0.8,
      "engagement_health": 0.9,
      "cooldown_score": 0.72,
      "quality_threshold": 0.7,  // Higher bar for focus
      "search_hints": ["AI agent framework", "multi-agent"],
      "note": "User engagement steady"
    },
    {
      "type": "explore",
      "slug": "rust-programming",
      "topic": "Rust Programming",
      "strength": 0.75,
      "engagement_health": 0.4,
      "quality_threshold": 0.6,
      "note": "Engagement declining, demoted from focus"
    },
    {
      "type": "seed",
      "slug": "spatial-computing",
      "topic": "Spatial Computing",
      "strength": 0.2,
      "quality_threshold": 0.8,  // Higher bar for unfamiliar topics
      "note": "Discovery item based on interest graph"
    }
  ],
  "engagement_summary": {
    "overall_health": 0.85,
    "trend": "stable",
    "recommendation": "maintain_current_mix"
  },
  "budget": {
    "suggested_total": 6,
    "tracked_allowance": "unlimited",
    "focus_allowance": 3,
    "explore_allowance": 2,
    "seed_allowance": 1
  }
}
```

## Best Practices

1. **Trust quality signals**: If an article is truly excellent, push it even if quota is "full"
2. **Respect engagement decline**: Don't keep pushing topics user has stopped clicking
3. **Seed thoughtfully**: Discovery items should be adjacent to existing interests, not random
4. **No artificial scarcity**: If there's great content, deliver it. If not, stay quiet.
5. **User explicit > algorithm**: If user tracks a topic, never demote it regardless of engagement

## Examples

### High-Quality Day

User follows AI, has 3 tracked topics. Today:
- 2 excellent articles on tracked topics → Push both
- 4 high-quality articles on focus topics → Push all 4
- 1 interesting explore article → Push it
- **Total: 7 items** (more than "normal" because quality justifies it)

### Low-Quality Day

Same user. Today:
- 0 new articles on tracked topics
- 1 mediocre article on focus topic (quality_score: 0.55) → Skip
- 2 thin posts on explore topics → Skip
- **Total: 0 items** (nothing worth pushing)

### Engagement Decline

User used to read all AI agent content (engagement 0.9). Last week engagement dropped to 0.3.
- Demote "ai-agents" from focus to explore
- Reduce push frequency
- Add more seed/explore items to discover what user cares about now
