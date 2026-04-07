# Eir Interest Rules

> For the OC content curator agent. Only what you need to know.

## Your Job

1. **Read directives**: `GET /oc/curation` → tells you what topics to find content for
2. **Find content**: Search/crawl based on directives
3. **Push content**: `POST /oc/content`
4. **Discover interests**: From user conversations → `POST /oc/interests/add`

That's it. The server handles strength, heat, scoring, and tier assignment.

## Curation Tiers

Directives from `GET /oc/curation` come in tiers:

| Tier | Meaning | Quality Bar |
|------|---------|-------------|
| **tracked** | User explicitly follows | 0.6 — always include |
| **focus** | heat > 5 or strength > 0.7 | 0.7 — higher bar |
| **explore** | heat 1–5 | 0.7 |
| **seed** | heat < 1 (discovery) | 0.8 — must be excellent |

## Budget

The `budget` field in curation response tells you:
- `suggested_total`: target items for the day
- `remaining_today`: how many more you can push

**Rules:**
- Quality > quantity — if nothing good, push nothing
- Tracked topics have no cap
- Respect the quality_threshold per directive
- Max 2 items from same topic group (unless exceptional)
- Cooldown is per-directive via the `freshness` field (not a fixed window). Examples: AI news = 1d, stable domains = 7d, academic = 14d
- If `cooldownUntil` is set and in the future, skip that directive unless content is truly exceptional

## Content Selection

For each directive, score candidates on:
- **Topic relevance** (25%) — matches the topic?
- **Source authority** (25%) — trusted source?
- **Freshness** (20%) — recent enough?
- **Depth** (15%) — substantial, not thin?
- **Novelty** (15%) — not a duplicate?

Minimum: `quality_threshold` from the directive (usually 0.6-0.8).

## Language

- `primary_language` from curation response = content language
- If `bilingual: true`, push two items per content (same slug, different `lang`)
- Interest labels always use `primary_language`

## Adding Interests

When you discover interests from conversations:
```
POST /oc/interests/add
{ "labels": ["AI Agents", "MCP Protocol"], "lang": "en" }
```
Server matches labels to the topic dictionary. Unknown labels get flagged for admin review.

## Interest Signals on Content

Every content item you push MUST include an `interests` field:

```json
"interests": {
  "anchor": ["ai-agents"],   // 1-3 slugs from your curation directives
  "related": [                // 2-5 adjacent discovery topics
    { "slug": "a2a-protocol", "label": "A2A Protocol" }
  ]
}
```

### How to set anchors
- Use the `slug` field from the directives you received in `GET /oc/curation`
- Each content item must have 1-3 anchors that match the directives
- The API validates anchors against user interests — mismatches are rejected with 400

### How to set related topics
- Pick 2-5 topics adjacent to the anchor but potentially new to the user
- `slug`: lowercase, hyphens, alphanumeric (e.g. "multi-agent-systems")
- `label`: human-readable in the content's language
- Topics not in the dictionary are auto-created as candidates
- These drive the "Explore More" section on the detail page

### Legacy: topicSlug
If `interests` is omitted, `topicSlug` is used as a single anchor. New content should always use `interests`.

## Best Practices

1. If content is truly excellent, push it even beyond budget
2. If nothing is worth reading, stay quiet (0 items is fine)
3. Seed items should be adjacent to existing interests, not random
4. Never override user's explicit tracking decisions
5. Use `GET /oc/sources` to dedup — don't re-push same URLs
