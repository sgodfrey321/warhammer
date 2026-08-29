from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .db import create_db_and_tables
from .routers import battles, rosters, unit_definitions


@asynccontextmanager
async def lifespan(app: FastAPI):
    create_db_and_tables()
    yield


app = FastAPI(title="Warhammer Manager API", lifespan=lifespan)

# Dev-only: allows the Vite dev server (a different origin) to call this API directly.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:5174"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(rosters.router)
app.include_router(unit_definitions.router)
app.include_router(battles.router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
