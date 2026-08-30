from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .db import create_db_and_tables
from .routers import army_rules, battles, layouts, primary_missions, rosters, secondary_missions, unit_definitions


@asynccontextmanager
async def lifespan(app: FastAPI):
    create_db_and_tables()
    yield


app = FastAPI(title="Warhammer Manager API", lifespan=lifespan)

# Dev-only: allows the Vite dev server (a different origin) to call this API directly --
# from this machine (localhost) and from any other machine on the home LAN (192.168.x.x),
# since the frontend is now exposed there too (see frontend/vite.config.ts).
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:5174"],
    allow_origin_regex=r"http://192\.168\.\d{1,3}\.\d{1,3}:517[34]",
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(rosters.router)
app.include_router(unit_definitions.router)
app.include_router(battles.router)
app.include_router(army_rules.router)
app.include_router(primary_missions.router)
app.include_router(secondary_missions.router)
app.include_router(layouts.router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
