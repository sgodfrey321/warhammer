# Build context is the repo root (not backend/) -- app/routers/*.py resolve their static
# JSON data files by walking up from __file__ assuming backend/ and tools/ are siblings
# (backend/app/routers/X.py -> ../../../../tools/{bsdata-indexer,gdmissions}/output/*.json).
# See docker-compose.yml's `context: .` / `dockerfile: backend/Dockerfile`.
FROM python:3.11-slim

WORKDIR /repo
COPY backend/ backend/
COPY tools/bsdata-indexer/output/ tools/bsdata-indexer/output/
COPY tools/gdmissions/output/ tools/gdmissions/output/

WORKDIR /repo/backend
# Editable install matters here, not just convenience -- a non-editable install copies app/
# into site-packages, which would silently break every __file__-relative path lookup above
# (they'd resolve inside site-packages instead of /repo). Editable keeps __file__ pointing at
# the real /repo/backend/app/... tree.
RUN pip install --no-cache-dir -e .

# Overrides db.py's default (which would otherwise resolve inside the image, not a durable
# path) -- backed by a named volume in docker-compose.yml so the database survives container
# recreation and image rebuilds.
ENV WARHAMMER_DB_PATH=/data/warhammer.db
VOLUME /data

EXPOSE 8000

COPY backend/docker-entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
ENTRYPOINT ["/entrypoint.sh"]
