import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse

from . import auth, db, games

STATIC = Path(os.environ.get("STATIC_DIR", "static")).resolve()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    await db.create_indexes()
    # What was still being written is lost in a restart.
    await db.games.update_many({"pending": {"$gt": 0}}, {"$set": {"pending": 0}})
    yield
    await db.client.close()


app = FastAPI(title="Geopoly", lifespan=lifespan)
app.add_middleware(GZipMiddleware, minimum_size=1000)
app.include_router(auth.router)
app.include_router(games.router)


@app.get("/{path:path}", include_in_schema=False)
def spa(path: str) -> FileResponse:
    if path.startswith("api/") or not STATIC.is_dir():
        raise HTTPException(404)
    file = (STATIC / path).resolve()
    if file.is_file() and file.is_relative_to(STATIC):
        return FileResponse(file)
    # Unknown paths are the app's own routes. No cache, so that a new build is picked up.
    return FileResponse(STATIC / "index.html", headers={"Cache-Control": "no-cache"})
