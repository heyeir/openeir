# Changelog

## 3.116.0 (pending)

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
