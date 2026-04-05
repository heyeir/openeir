# Eir Rendering & Content Requirements

> Single source of truth for all content field constraints.
> Used by: writer prompts, post_content.py validation, API validation, front-end rendering.

---

## Field Reference

### dot (L0 — the dot on canvas)

| Field | Type | Recommended | Hard Limit | Notes |
|-------|------|-------------|------------|-------|
| `hook` | string | ≤10 CJK chars / ≤6 EN words | **30 chars** (API rejects) | Creates curiosity gap. No hype words ("Breaking", "Exciting"). Rendered as single-line label on the dot. |
| `category` | enum | — | `focus` \| `attention` \| `seed` \| `whisper` | Determines dot visual style. Whispers always use `whisper`. |
| `color_hint` | enum | — | `blue` \| `gold` \| `amber` \| `cyan` \| `green` \| `purple` \| `red` | Whispers always use `amber`. |

### l1 (card — what the user sees first)

| Field | Type | Recommended | Hard Limit | Notes |
|-------|------|-------------|------------|-------|
| `title` | string | 15-40 CJK chars / 8-15 EN words | **200 chars** (API rejects) | Opinionated, not a headline. Must be in `lang`. |
| `summary` | string | 50-80 words | — | 2-3 sentences. Advances beyond the title — don't repeat. |
| `key_quote` | string | 1 sentence | — | Best direct quote from sources. Use `""` if none. |
| `via` | **string[]** | — | — | **Must be an array.** Auto-derived from `sources[].name`. Pipeline (`post_content.py`) populates it; API also falls back to `sources[].name` if empty. Writer should NOT set this. |
| `bullets` | string[] | 3-4 items | 10 items (API rejects) | Each: ≤20 CJK chars / ≤50 EN chars. Don't repeat summary. |

### l2 (depth — expanded view)

| Field | Type | Recommended | Hard Limit | Notes |
|-------|------|-------------|------------|-------|
| `content` | string | 200-600 CJK chars / 150-400 EN words | — | 2-4 paragraphs separated by `\n\n`. Starts where summary left off. |
| `bullets` | array | 3-5 items | — | Each: `{text: string, confidence: "high"\|"medium"\|"low"}`. Concrete facts with numbers/names. Every bullet must have supporting detail in `content`. |
| `context` | string | 1-2 sentences | — | "SO WHAT for the reader." Be specific and direct — address the reader. |
| `eir_take` | string | 1 sentence | — | Eir's sharp opinion. **PUBLIC** (visible on share pages) — no user-specific info. |
| `related_topics` | string[] | 3-5 items | — | Human-readable phrases in `lang`. NOT slugs. e.g. `"向量检索与ANN算法"` ✅, `"vector-search-ann"` ❌ |

### sources (provenance — machine-readable)

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `url` | string | **Yes** | Must be valid URL. Used for server-side dedup — duplicate URLs are rejected. |
| `title` | string | No | Original article title. |
| `name` | string | No | Publisher/source name (e.g. "MIT Technology Review"). This is what `l1.via` selects from. |
| `publish_time` | string | No | ISO date or date string from source. |

### Top-level item fields

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `lang` | `"zh"` \| `"en"` | **Yes** | Language of this document's content. Determines which `{contentGroup}_{lang}` document is created. Not locale, not source language — the language the content is written in. |
| `slug` | string | No | Human-readable identifier. Falls back to `contentGroup` if omitted. |
| `topicSlug` | string | No | Links content to a user interest topic for cooldown tracking. |
| `dot` | object | **Yes** | See dot section above. |
| `l1` | object | **Yes** | See l1 section above. `l1.title` is required. |
| `l2` | object | No | See l2 section above. Strongly recommended. |
| `sources` | array | No | See sources section above. At least 1 recommended. |

---

## via vs sources

`via` = `sources[].name` — the full set, not a subset.

| | `sources[]` | `l1.via` |
|---|---|---|
| **Purpose** | Machine: dedup, provenance, linking | Human: display attribution on card |
| **Contains** | Full metadata (url, title, name) | Just the names |
| **Type** | `Array<{url, title, name}>` | `string[]` |
| **Set by** | Writer (required) | `post_content.py` (auto-derived); API also falls back to `sources[].name` if empty |
| **Example** | `[{url: "...", name: "MIT Tech Review"}, {url: "...", name: "ArXiv"}]` | `["MIT Tech Review", "ArXiv"]` |

**Writers only need to set `sources[]`.** The pipeline auto-populates `via` from `sources[].name`; the API also falls back to `sources[].name` if `via` is empty. If the writer includes `via` it will be overwritten.

---

## lang field

`lang` means: **"what language is this content written in?"**

- Set by pipeline's `output_lang` parameter
- Each language version is a **separate document** with ID `{contentGroup}_{lang}`
- For bilingual users: pipeline generates two items with same `slug`/`topicSlug` but different `lang`
- `lang` is NOT locale (UI language) and NOT source_lang (language of source articles)

| Field | Meaning | Set by |
|-------|---------|--------|
| `lang` | Content language | Pipeline `output_lang` |
| `source_lang` | **Deprecated.** Was: dominant source language. Now: unused by API. | — |
| `locale` (user pref) | UI language (dates, buttons) | User settings |

---

## Whisper-specific overrides

Whispers share the same dot/l1/l2 structure but with different field semantics:

| Field | Whisper value | Notes |
|-------|--------------|-------|
| `dot.category` | Always `"whisper"` | Server overrides to whisper |
| `dot.color_hint` | Always `"amber"` | Server overrides to amber |
| `dot.hook` | ≤10 chars | Same as content recommended limit |
| `l1.participants` | `"user+eir"` | Server defaults if omitted |
| `l1.via` | `["OpenClaw"]` | Server defaults if omitted |
| `l2.tension` | Required | "X vs Y" format |
| `l2.unresolved` | Required | Open question from conversation |
| `l2.thinking_path` | Required, 3-5 items | Nodes of reasoning progression |
| `l2.eir_role` | Required | `"challenger"` \| `"extender"` \| `"mirror"` \| `"catalyst"` |

---

## Null handling

**Never set any field to `null`.** The front-end renders null as literal "placeholder" text.

| Instead of | Use |
|-----------|-----|
| `null` | `""` (empty string) |
| `null` | `[]` (empty array) |
| `{field: null}` | Omit the field entirely |

---

## Validation summary

### API rejects (400 error)

- `dot` missing or not an object
- `dot.hook` empty or >30 chars
- `dot.category` not in allowed enum
- `dot.color_hint` not in allowed enum
- `l1` missing or not an object
- `l1.title` empty or >200 chars
- `l1.via` present but not an array
- `l1.bullets` present but not an array, or >10 items
- `sources[].url` missing or not a valid URL
- `sources` >10 items per content item
- `lang` present but not `"zh"` or `"en"`
- `items` empty, not an array, or >20 items

### API skips (returned as `status: "skipped"`)

- Any `sources[].url` already exists for this user → `duplicate source_url`

### Pipeline should reject (pre-POST)

- `l1.title` missing → don't POST, file is broken
- `l2.content` <300 chars → quality too low
- `dot.hook` >15 chars → trim or regenerate (API allows up to 30 but rendering truncates)

---

## Content vs Whisper: ID format

Both use the same ID scheme:

```
{8-char contentGroup}_{lang}    e.g. a3k9m2x7_zh
```

- `contentGroup`: 8-char base64url, globally unique, registered in `short_ids` container
- All language versions of the same item share the `contentGroup`
- Content stored in `content_items_v2`, whispers in `whispers_v2`
