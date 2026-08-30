#!/bin/sh
set -e

# Idempotent (upserts by source_entry_id, see scripts/import_unit_definitions.py) -- safe to
# run on every startup, so a fresh volume gets seeded automatically and an image rebuilt after
# a dataslate update re-syncs existing data too. No separate manual step ever needed.
python -m scripts.import_unit_definitions

exec python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
