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
| **focus** | Strong interest, good engagement | 0.7 — higher bar |
| **explore** | Moderate interest or declining focus | 0.6 |
| **seed** | Discovery items | 0.8 — must be excellent |

## Budget

The `budget` field in curation response tells you:
- `suggested_total`: target items for the day
- `remaining_today`: how many more you can push

**Rules:**
- Quality > quantity — if nothing good, push nothing
- Tracked topics have no cap
- Respect the quality_threshold per directive
- Max 2 items from same topic group (unless exceptional)
- 36h cooldown between same-topic pushes

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

## Best Practices

1. If content is truly excellent, push it even beyond budget
2. If nothing is worth reading, stay quiet (0 items is fine)
3. Seed items should be adjacent to existing interests, not random
4. Never override user's explicit tracking decisions
5. Use `GET /oc/sources` to dedup — don't re-push same URLs
