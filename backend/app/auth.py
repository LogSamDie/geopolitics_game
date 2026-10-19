"""Sign up, log in and log out with a session cookie.

Passwords are hashed with scrypt from the standard library. A session is a random token
stored in MongoDB and sent to the browser as an HttpOnly cookie.
"""

import hashlib
import hmac
import secrets
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from pymongo.errors import DuplicateKeyError

from . import db

COOKIE = "session"
router = APIRouter(prefix="/api/auth")


class Credentials(BaseModel):
    username: str = Field(min_length=2, max_length=32, pattern=r"^[A-Za-z0-9_.-]+$")
    password: str = Field(min_length=6, max_length=128)


class User(BaseModel):
    id: str
    username: str


def hash_password(password: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    key = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1)
    return f"{salt.hex()}:{key.hex()}"


def verify_password(password: str, stored: str) -> bool:
    salt = bytes.fromhex(stored.split(":")[0])
    return hmac.compare_digest(hash_password(password, salt), stored)


async def current_user(session: Annotated[str | None, Cookie()] = None) -> User:
    """Dependency for routes that need a logged-in user."""
    found = await db.sessions.find_one({"_id": session}) if session else None
    user = await db.users.find_one({"_id": found["user_id"]}) if found else None
    if user is None:
        raise HTTPException(401, "Please log in")
    return User(id=str(user["_id"]), username=user["username"])


async def start_session(response: Response, user: db.Document) -> User:
    token = secrets.token_urlsafe(32)
    await db.sessions.insert_one(
        {"_id": token, "user_id": user["_id"], "created": datetime.now(UTC)}
    )
    response.set_cookie(COOKIE, token, httponly=True, samesite="lax", max_age=30 * 24 * 3600)
    return User(id=str(user["_id"]), username=user["username"])


@router.post("/register")
async def register(credentials: Credentials, response: Response) -> User:
    user = {
        "username": credentials.username,
        "password": hash_password(credentials.password),
        "created": datetime.now(UTC),
    }
    try:
        user["_id"] = (await db.users.insert_one(user)).inserted_id
    except DuplicateKeyError:
        raise HTTPException(409, "That username is taken") from None
    return await start_session(response, user)


@router.post("/login")
async def login(credentials: Credentials, response: Response) -> User:
    user = await db.users.find_one({"username": credentials.username})
    if user is None or not verify_password(credentials.password, user["password"]):
        raise HTTPException(401, "Wrong username or password")
    return await start_session(response, user)


@router.post("/logout", status_code=204)
async def logout(response: Response, session: Annotated[str | None, Cookie()] = None) -> None:
    await db.sessions.delete_one({"_id": session})
    response.delete_cookie(COOKIE)


@router.get("/me")
async def me(user: Annotated[User, Depends(current_user)]) -> User:
    return user
