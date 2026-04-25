# Changelog

## 3.118.0 (pending)

Node.js dependency completely removed — the Eir connect script is now pure Python (no more `connect.mjs`). The skill requires only Python 3.10+ with no external packages.

Interest extraction reworked to understand general content interests from conversation, rather than reading specific files. Writer prompts use softer "audience context" language throughout.

Also: `SEARCH_API_KEY` added to declared environment variables, `package.json` removed.

## 3.117.0 (2026-04-25)

Removed the unnecessary `package.json` that was triggering Node.js dependency signals. Added `SEARCH_API_KEY` to declared environment variables. Interest extraction prompt no longer references specific files — just asks the user or reads available context. Code comments cleaned up.

## 3.116.0 (2026-04-25)

Daily Brief now stays local — no more API call, brief is delivered directly to your configured channel with a link to explore more on [heyeir.com](https://www.heyeir.com).

`l2.context` and `eir_take` are now optional. Skip them entirely or leave empty — useful if you prefer factual summaries without editorial commentary.

Personalization is more flexible: provide audience context however you like (or don't). The skill no longer prescribes where that context comes from.

Also fixed: metadata now correctly declares Node.js as optional and documents environment variables. Security docs consolidated into SECURITY.md.

## 3.115.0 (2026-04-24)

Eir mode and Standalone mode now have separate setup flows with a Getting Started guide that asks which mode to use first.

Writer prompts are loaded dynamically based on mode — task files no longer embed the full prompt text, making them smaller and mode-switching cleaner.

First-run experience improved: workspace auto-creates `config/settings.json` with sensible defaults. Windows users get proper UTF-8 output.

Search quality: 2-pass entity refinement now works for all topic tiers, not just focus. CJK topic labels handled correctly with hash fallback for slugs.

## 3.114.0 (2026-04-23)

Standalone and Eir modes cleanly separated — different code paths, different privacy guarantees. Security docs rewritten with clear data flow tables per mode.

Removed legacy whisper/transcript references. Credentials use openclaw config storage instead of environment variables.
