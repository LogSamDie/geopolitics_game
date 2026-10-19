"""MongoDB connection. Three collections: users, sessions and games."""

import os
from typing import Any

from pymongo import AsyncMongoClient

Document = dict[str, Any]

client: AsyncMongoClient[Document] = AsyncMongoClient(
    os.environ.get("MONGO_URL", "mongodb://localhost:27017"), serverSelectionTimeoutMS=3000
)
database = client[os.environ.get("MONGO_DB", "geopolitics")]
users = database["users"]
sessions = database["sessions"]
games = database["games"]


async def create_indexes() -> None:
    await users.create_index("username", unique=True)
    await games.create_index("owner")
