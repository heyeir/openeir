# Candidates JSON Format Specification

This document defines the expected format of `candidates.json`, which is the handoff point between candidate selection (agent-driven) and crawling/task building (automated scripts).

## Location

`data/v9/candidates.json`

## Structure

```json
{
  "candidates": [
    {
      "content_slug": "string (required) — kebab-case identifier, 3-6 words",
      "matched_topic_slug": "string (required) — must match a directive slug",
      "suggested_angle": "string (required) — editorial angle in output language",
      "reason": "string (optional) — why this candidate was selected",
      "priority": "string (optional) — 'high' | 'medium' | 'low', default 'medium'",
      "source_refs": [1, 3, 5]
    }
  ],
  "skipped_topics": [
    {"slug": "...", "reason": "why skipped"}
  ],
  "selected_at": "ISO 8601 timestamp"
}
```

## Agent Responsibilities

The agent ONLY decides:
1. **Which topics** to cover (matched_topic_slug)
2. **What angle** to take (suggested_angle)
3. **Which articles** are relevant (source_refs — article indices from the topic file)
4. **Content slug** (descriptive kebab-case name)

The agent does **NOT** need to provide `source_urls` or `source_titles`.
These are auto-filled by `resolve_sources.py` from the topic files.

## Field Details

### Required Fields (agent outputs these)

| Field | Type | Description |
|-------|------|-------------|
| `content_slug` | string | Unique identifier. Kebab-case, 3-6 words. Used as filename and API slug. |
| `matched_topic_slug` | string | The directive topic this belongs to. Must match a topic file slug. |
| `suggested_angle` | string | The editorial angle — what makes this worth covering. |

### Optional Fields (agent may output these)

| Field | Type | Description |
|-------|------|-------------|
| `source_refs` | int[] | 1-based article indices from the topic file. If omitted, all articles are used. |
| `reason` | string | Why this candidate was selected (for audit trail). |
| `priority` | string | `high` / `medium` / `low`. Default: `medium`. |

### Auto-filled Fields (script fills these)

| Field | Type | Description |
|-------|------|-------------|
| `source_urls` | string[] | Resolved from source_refs or all topic articles. |
| `source_titles` | object | Map of URL → article title. |

## Pipeline Flow

```
candidate_selector.py → topic files (articles with URLs)
         ↓
Agent reads topics → outputs candidates.json (slug + angle + source_refs)
         ↓
resolve_sources.py → fills source_urls from topic files
         ↓
crawl.py → fetches full content
         ↓
task_builder.py → bundles into task files
```

## Validation

- `content_slug` must be unique across all candidates
- `matched_topic_slug` must match a topic file in `data/v9/topics/`
- `source_refs` indices must be within range of the topic file's articles array
- **All sources for one candidate must be about the same event/narrative.** Never bundle unrelated stories into one candidate.
- No `null` values — use `""` or `[]` for empty fields

## Public Content Dedup

The `index.json` at `data/v9/topics/index.json` may contain `public_picks_context`. Content already in the public pool must NOT be duplicated.

## content_slug Rules

- Descriptive, kebab-case, based on the specific article content
- 3-6 words, lowercase, hyphens only (e.g. "coreweave-anthropic-cloud-deal")
- Must be unique across candidates
- Will be used as both the filename and the content ID in the API
