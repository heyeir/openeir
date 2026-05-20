# Candidates JSON Format Specification

This document defines the expected format of `candidates.json`, which is the handoff point between candidate selection (agent-driven) and crawling/task building (automated scripts).

## Location

`data/v9/candidates.json`

## Structure

```json
{
  "candidates": [
    {
      "content_slug": "string (required) — kebab-case identifier, 3-6 words, e.g. 'openai-gpt-5-launch'",
      "matched_topic_slug": "string (required) — must match a directive slug, e.g. 'ai-industry-news'",
      "suggested_angle": "string (required) — editorial angle in output language",
      "reason": "string (optional) — why this candidate was selected",
      "priority": "string (optional) — 'high' | 'medium' | 'low', default 'medium'",
      "source_urls": [
        "string (required, 1-5 URLs) — URLs to crawl for full content"
      ],
      "source_titles": {
        "https://example.com/article": "Article Title"
      }
    }
  ],
  "selected_at": "ISO 8601 timestamp"
}
```

## Field Details

### Required Fields

| Field | Type | Description |
|-------|------|-------------|
| `content_slug` | string | Unique identifier for this content piece. Used as filename and API slug. Must be kebab-case, 3-6 words. |
| `matched_topic_slug` | string | The directive topic this belongs to. Must match a slug from directives/interests. Used as `topicSlug` in generated content. |
| `suggested_angle` | string | The editorial angle — what makes this worth covering. In the output language. |
| `source_urls` | string[] | 1-5 URLs to crawl. Prefer diverse domains. At least one must be crawlable. |

### Optional Fields

| Field | Type | Description |
|-------|------|-------------|
| `reason` | string | Why this candidate was selected (for audit trail). |
| `priority` | string | `high` / `medium` / `low`. Affects generation order. Default: `medium`. |
| `source_titles` | object | Map of URL → article title (helps crawl quality scoring). |

## Downstream Usage

1. **`crawl.py`** reads `candidates.json`, crawls each `source_urls` entry, saves content to `data/v9/snippets/{url_hash}.json`.
2. **`task_builder.py`** reads crawled candidates, bundles source text + writer prompt into task files at `data/v9/tasks/{content_slug}.json`.

## How Candidates Are Created

### Eir Mode (cron-driven)
The agent reads per-topic files from `data/v9/topics/`, evaluates search results, and writes `candidates.json` directly.

### Standalone Mode (manual)
1. Run `python3 -m pipeline.candidate_selector` → generates topic files in `data/v9/topics/`
2. Review topic files and create `candidates.json` following the format above
3. Run `python3 -m pipeline.crawl` → crawls candidate URLs

## Validation

- `content_slug` must be unique across all candidates
- `matched_topic_slug` should match a known directive/interest slug
- `source_urls` must contain at least 1 valid HTTP(S) URL
- **`source_urls` MUST be copied verbatim from the topic file's `articles[].url` field.** Do NOT invent, modify, extend, or shorten URLs. If a URL appears truncated in the topic file, use it exactly as-is — the pipeline handles truncated URLs internally.
- **All `source_urls` must be about the same event/narrative.** Never bundle unrelated stories into one candidate just because they share a topic or appeared in the same time window. If two articles cover different events (e.g. "AI startup steals art" vs "AI beats doctors in ER"), they MUST be separate candidates — even if both fall under the same topic_slug.
- No `null` values — use `""` or `[]` for empty fields

## Public Content Dedup

The `index.json` file at `data/v9/topics/index.json` may contain a `public_picks_context` field. This lists content already published in the public pool. **Do NOT create candidates that cover the same event or angle as any item listed there.** This prevents duplication between public and private content.
