"""FastAPI application. Serves the API and, in production, the built Svelte app."""

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse

from . import auth, db, games

STATIC = Path(os.environ.get("STATIC_DIR", "static")).resolve()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    await db.create_indexes()
    yield
    await db.client.close()


app = FastAPI(title="Geopoly", lifespan=lifespan)
app.add_middleware(GZipMiddleware, minimum_size=1000)
app.include_router(auth.router)
app.include_router(games.router)


@app.get("/{path:path}", include_in_schema=False)
def spa(path: str) -> FileResponse:
    """Serve the built frontend; unknown paths get index.html so the app can route them."""
    if path.startswith("api/") or not STATIC.is_dir():
        raise HTTPException(404)
    file = (STATIC / path).resolve()
    if file.is_file() and file.is_relative_to(STATIC):
        return FileResponse(file)
    # Always revalidated, so a new build is picked up; the assets it names have hashed filenames.
    return FileResponse(STATIC / "index.html", headers={"Cache-Control": "no-cache"})
