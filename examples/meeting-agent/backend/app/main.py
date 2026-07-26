from __future__ import annotations
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from .db import init_db
from .api import auth, tasks, recording, transcript, minutes, knowledge, templates
from .services.lake_client import lake


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    await templates.seed_builtin_templates()
    yield
    await lake.close()


app = FastAPI(lifespan=lifespan, title="Meeting Agent v0.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(tasks.router)
app.include_router(recording.router)
app.include_router(transcript.router)
app.include_router(minutes.router)
app.include_router(knowledge.router)
app.include_router(templates.router)

static_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "frontend", "dist")
index_html = os.path.join(static_dir, "index.html")
if os.path.isdir(static_dir):
    app.mount("/assets", StaticFiles(directory=os.path.join(static_dir, "assets")), name="assets")

    @app.get("/{full_path:path}")
    async def spa_fallback(full_path: str):
        candidate = os.path.join(static_dir, full_path)
        if full_path and os.path.isfile(candidate):
            return FileResponse(candidate)
        return FileResponse(index_html)
