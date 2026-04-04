# eir-daily-content-curator — Review & Findings

> Reviewed: 2026-04-03 by Eir (content agent)
> Tested against: `https://api.heyeir.com/api/oc` (production)

## API Endpoint Test Results

| # | Endpoint | Method | Status | Notes |
|---|----------|--------|--------|-------|
| 1 | `/profile` | GET | ✅ 200 | Works, returns full profile |
| 2 | `/interests` | GET | ❌ 404 | **Not deployed** — skill references it |
| 3 | `/interests` | POST | ❌ 404 | **Not deployed** — skill references it |
| 4 | `/analyze-interests` | POST | ❌ 404 | **Not deployed** — eir-interest-curator depends on it |
| 5 | `/content` | GET | ✅ 200 | Returns directives + content_prompt |
| 6 | `/content` | POST (v2 flat) | ❌ 400 | "No items provided" — **v2 flat format not supported** |
| 7 | `/content` | POST (v1 `{items:[...]}`) | ✅ 200 | Works, but requires top-level `dot`+`l1` (not just `locales`) |
| 8 | `/content/:id` | GET | ✅ 200 | Returns full content with `locales` structure |
| 9 | `/content/:id/locale/:lang` | PATCH | ✅ 200 | Works for adding translations |
| 10 | `/content/:id/translation` | POST | ❌ 404 | **Not deployed** — post_translation.py depends on it |
| 11 | `/sources` | GET | ✅ 200 | Returns used URLs |
| 12 | `/whispers` | POST | ✅ 200 | Works |
| 13 | `/content/:id` | DELETE | ❌ 404 | Not available |
| 14 | `/refresh-key` | POST | ✅ 200 | Works (⚠️ rotates key immediately) |

## Critical: API is v1, not v2

The live API still uses v1 format:
- POST `/content` requires `{items: [{...}]}` wrapper
- Content is stored in `locales.{lang}` structure, not flat
- Translation uses `PATCH /content/:id/locale/:lang`, not `POST .../translation`
- `topicSlug` (camelCase), not `topic_slug` (snake_case)
- `publishTime` (camelCase), both forms accepted on input

## Bugs Found in Scripts (all fixed in this PR unless noted)

### B1: `post_content.py` — WORKSPACE path wrong
```python
WORKSPACE = Path(__file__).parent.parent  # → scripts/pipeline → scripts
```
Should be `.parent.parent.parent` to reach skill root. Currently DATA points to `scripts/data/` instead of skill `data/`.

### B2: `post_content.py` — sends v2 flat format, API requires v1 `{items:[...]}`
The script sends:
```json
{"lang": "zh", "slug": "...", "l1": {...}, ...}
```
But API expects:
```json
{"items": [{"dot": {...}, "l1": {...}, "locales": {...}, ...}]}
```

### B3: `post_content.py` — uses `topic_slug` (snake_case), API stores `topicSlug` (camelCase)

### B4: `post_content.py` — checks `resp.get("status") not in ("created", "accepted")` but API returns `"accepted"` in results array, not top-level status

### B5: `post_translation.py` — calls `POST /content/:id/translation` which is 404
Should use `PATCH /content/:id/locale/:lang` instead.

### B6: `post_translation.py` — WORKSPACE path also wrong (same as B1)

### B7: `generate_dispatcher.py` — WORKSPACE path uses different calculation
```python
WORKSPACE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
```
From `scripts/pipeline/` → `scripts/` (wrong, should go one more level up)

### B8: `interest_extractor.py` — references `GET /interests` and `POST /interests` which are 404

### B9: `whisper_extract.py` — works (POST /whispers is live), but essay generation is placeholder

### B10: ~~`deliver.py` — WORKSPACE path wrong~~
`deliver.py` actually uses `.parent.parent.parent` (3 levels) — **this is correct**.
But `post_content.py` and `post_translation.py` originally used only 2 levels — **fixed**.

### B11: `SKILL.md` — API table references `POST /content/:id/translation` (404)

### B12: `eir-api.md` — documents `GET /interests`, `POST /interests`, `POST /analyze-interests` which are all 404

### B13: `content_prompt` from API uses `locales.{lang}` and `topicSlug` — conflicts with skill's writer-prompt-eir.md which uses flat format and `topic_slug`

## Suggested Fixes (all implemented and tested in this PR)

### Fix 1: `post_content.py` — adapted to v1 API ✅ TESTED
- Fixed WORKSPACE path (3 levels)
- Wrapped payload in `{items: [...]}`
- Used `topicSlug` not `topic_slug`
- Included `locales.{lang}` structure with top-level `l1`/`l2`
- Fixed response parsing for v1 format
- **Test result**: Successfully posted content ID `ci_u_3a638cdb-..._3ldt`

### Fix 2: `post_translation.py` → uses PATCH locale ✅ TESTED
- Uses `PATCH /content/:id/locale/:lang` instead of `POST .../translation`
- Fixed WORKSPACE path
- **Test result**: Successfully added en locale to test content

### Fix 3: `generate_dispatcher.py` — fixed WORKSPACE path ✅

### Fix 4: `interest_extractor.py` — uses /profile instead of /interests ✅ TESTED
- Reads interests from `GET /profile` (short_term_interests + long_term_interests)
- Removed POST /interests call (404)
- **Test result**: Successfully synced 77 topics from Eir profile

### Fix 5: SKILL.md — updated field names ✅

### Fix 6: writer-prompt-eir.md — added API compatibility notes ✅

### Fix 7: eir-api.md — added live API status warning ✅

## Improvement Suggestions (not implemented, for future consideration)

1. **Config path inconsistency**: `post_content.py` reads from `~/.openclaw/skills/eir/config.json` but skill stores config in `config/eir.json`. Should be unified.
2. **`cache_manager.py` hardcodes DATA_DIR**: `Path.home() / ".openclaw" / "workspace-content" / "data"` — works for deployed setup but breaks standalone use. Should derive from WORKSPACE.
3. **`settings.json` defaults to standalone mode**: New users following Eir setup may miss switching mode.
4. **`content_prompt` from API conflicts with local `writer-prompt-eir.md`**: The API prompt uses `locales.{lang}` nesting and `topicSlug`, while the local prompt uses flat format and `topic_slug`. Need to decide which is authoritative.
5. **`interest_extractor.py` regex-based extraction is very basic**: Only matches hardcoded English patterns. Won't catch Chinese-language interests.
6. **`sources.json` has no Chinese sources**: All 28 feeds are English. For Chinese-primary users this limits coverage.
7. **`refresh-key` endpoint is dangerous**: Rotated production key during testing. SKILL.md should warn about this.
8. **`datetime.utcnow()` deprecation**: Multiple scripts use deprecated `datetime.utcnow()`. Should use `datetime.now(timezone.utc)`.
9. **Test content created**: Content ID `ci_u_..._wfwr` and `ci_u_..._3ldt` are test data in production (DELETE not available).
