from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Attach a root handler so our own `app.*` loggers (e.g. app.simulate's per-request
# printouts) show up in the console alongside uvicorn's logs. basicConfig is a no-op
# if a handler is already configured, so this is safe under uvicorn/pytest/gunicorn.
logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")

from .db import create_db_and_tables
from .routers import (
    army_rules,
    auth,
    battles,
    detachments,
    layouts,
    primary_missions,
    rosters,
    secondary_missions,
    simulate,
    unit_definitions,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    create_db_and_tables()
    yield


app = FastAPI(title="Warhammer Manager API", lifespan=lifespan)

# Dev-only: allows the Vite dev server (a different origin) to call this API directly --
# from this machine (localhost) and from any other machine on a private LAN (192.168/16,
# 10/8, 172.16/12), since the frontend is exposed there too (see frontend/vite.config.ts).
# Port 80 / no port covers the Docker frontend.
_OCTET = r"(?:25[0-5]|2[0-4]\d|1?\d?\d)"
_ORIGIN_REGEX = (
    r"^http://(?:localhost|127\.0\.0\.1"
    rf"|192\.168\.{_OCTET}\.{_OCTET}"
    rf"|10\.{_OCTET}\.{_OCTET}\.{_OCTET}"
    rf"|172\.(?:1[6-9]|2\d|3[01])\.{_OCTET}\.{_OCTET})"
    r"(?::(?:517[34]|80))?$"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:5174"],
    allow_origin_regex=_ORIGIN_REGEX,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(rosters.router)
app.include_router(unit_definitions.router)
app.include_router(battles.router)
app.include_router(army_rules.router)
app.include_router(detachments.router)
app.include_router(primary_missions.router)
app.include_router(secondary_missions.router)
app.include_router(layouts.router)
app.include_router(simulate.router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
