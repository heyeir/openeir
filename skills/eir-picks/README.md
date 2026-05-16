# Eir Picks — Public Content Pool Overlay

This skill evaluates content from Eir's shared public pool and generates personalized connection overlays.

## Dependencies

This skill shares the pipeline infrastructure with `eir-daily-content-curator`. The Python modules (`workspace.py`, `config.py`) are imported from the parent skill's `scripts/pipeline/` package.

## Quick Start

```bash
# Ensure eir-daily-content-curator is installed and configured first
# Then run picks evaluation standalone:
cd /path/to/eir-daily-content-curator
python3 -c "
from pipeline.picks_overlay import get_cached_curation, post_overlays
curation = get_cached_curation()
print(f'Public picks available: {len(curation[\"publicPicks\"])}')
"
```

See `SKILL.md` for full documentation.
