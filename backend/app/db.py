import gzip
import json
import math
import os
from typing import Any

from bson import ObjectId
from pymongo import AsyncMongoClient

Document = dict[str, Any]

client: AsyncMongoClient[Document] = AsyncMongoClient(
    os.environ.get("MONGO_URL", "mongodb://localhost:27017"), serverSelectionTimeoutMS=3000
)
database = client[os.environ.get("MONGO_DB", "geopolitics")]
users = database["users"]
sessions = database["sessions"]
games = database["games"]
events = database["events"]


async def create_indexes() -> None:
    await users.create_index("username", unique=True)
    await games.create_index("owner")
    await events.create_index(["game", "last"])
    await sessions.create_index("created", expireAfterSeconds=30 * 24 * 3600)


async def save_events(game_id: ObjectId, batch: list[Document]) -> None:
    data = gzip.compress(json.dumps(batch, separators=(",", ":")).encode())
    await events.insert_one(
        {"game": game_id, "first": batch[0]["seq"], "last": batch[-1]["seq"], "data": data}
    )


async def load_events(
    game_id: ObjectId, after: int = 0, before: float = math.inf
) -> list[Document]:
    """The events with a number between these two, in order."""
    query = {"game": game_id, "last": {"$gt": after}, "first": {"$lt": before}}
    records = await events.find(query).sort("last").to_list()
    batches = [json.loads(gzip.decompress(r["data"])) for r in records]
    return [e for batch in batches for e in batch if after < e["seq"] < before]
