"""Anyone with a game's link can read it; only its owner can play it.

A game document holds the current state and the notes. Its events are stored apart, see db.py.
"""

import random
from datetime import UTC, datetime
from typing import Annotated, Literal

from bson import ObjectId
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from . import commentary, db, npc
from .auth import User, current_user
from .countries import COUNTRIES
from .engine import NPC_NAMES, Country, Event, Game, RuleError, State, Turn

router = APIRouter(prefix="/api")


class Reinforce(BaseModel):
    kind: Literal["reinforce"]
    country: str
    soldiers: int


class Transfer(BaseModel):
    kind: Literal["transfer"]
    source: str
    target: str
    soldiers: int


class Attack(BaseModel):
    kind: Literal["attack"]
    source: str
    target: str


class Simple(BaseModel):
    kind: Literal["roll", "fight", "stop", "end_turn"]


Command = Annotated[Reinforce | Transfer | Attack | Simple, Field(discriminator="kind")]


class NewGame(BaseModel):
    country: str


class GameSummary(BaseModel):
    id: str
    created: datetime
    human: str
    country: str
    turn: Turn
    countries: int


class GameView(BaseModel):
    id: str
    owner: str
    state: State
    events: list[Event]
    notes: list[commentary.Note]
    pending: int  # jobs still being written


@router.get("/countries")
def list_countries() -> list[Country]:
    return list(COUNTRIES.values())


@router.post("/games", status_code=201)
async def create_game(
    body: NewGame, user: Annotated[User, Depends(current_user)], tasks: BackgroundTasks
) -> GameView:
    if body.country not in COUNTRIES:
        raise HTTPException(422, "Unknown country")
    others = [c for code, c in COUNTRIES.items() if code != body.country]
    chosen = [COUNTRIES[body.country], *random.sample(others, len(NPC_NAMES))]
    countries = [c.model_copy() for c in chosen]
    game = Game.new(user.username, countries)
    npc.run(game)
    jobs = commentary.jobs(game)
    doc: db.Document = {
        "owner": user.id,
        "created": datetime.now(UTC),
        "version": 1,
        "state": game.state.model_dump(),
        "pending": len(jobs),
    }
    doc["_id"] = ObjectId()
    await db.save_events(doc["_id"], [e.model_dump() for e in game.events])
    await db.games.insert_one(doc)
    tasks.add_task(commentary.write, doc["_id"], jobs, game.state.players)
    return view(doc, game.state, game.events)


@router.get("/games")
async def list_games(user: Annotated[User, Depends(current_user)]) -> list[GameSummary]:
    summaries = []
    async for doc in db.games.find({"owner": user.id}, {"notes": 0}).sort("created", -1):
        game = Game(State.model_validate(doc["state"]))
        summaries.append(
            GameSummary(
                id=str(doc["_id"]),
                created=doc["created"],
                human=game.human.id,
                country=game.state.countries[0].name,
                turn=game.turn,
                countries=len(game.countries_of(game.human.id)),
            )
        )
    return summaries


@router.get("/games/{game_id}")
async def get_game(game_id: str, after: Annotated[int, Query(ge=0, le=10**9)] = 0) -> GameView:
    doc = await load(game_id)
    events = [Event.model_validate(e) for e in await db.load_events(doc["_id"], after)]
    return view(doc, State.model_validate(doc["state"]), events)


@router.post("/games/{game_id}/commands")
async def play(
    game_id: str,
    command: Command,
    user: Annotated[User, Depends(current_user)],
    tasks: BackgroundTasks,
) -> GameView:
    doc = await load(game_id)
    if doc["owner"] != user.id:
        raise HTTPException(403, "Only the owner can play this game")
    game = Game(State.model_validate(doc["state"]))
    if game.turn.phase == "over":
        raise HTTPException(409, "The game is over")
    try:
        apply(game, command)
    except RuleError as error:
        raise HTTPException(422, str(error)) from None
    npc.run(game)
    jobs = commentary.jobs(game)
    result = await db.games.update_one(
        {"_id": doc["_id"], "version": doc["version"]},
        {
            "$set": {"state": game.state.model_dump()},
            "$inc": {"version": 1, "pending": len(jobs)},
        },
    )
    if result.matched_count == 0:
        raise HTTPException(409, "The game changed in the meantime, reload it")
    try:
        await db.save_events(doc["_id"], [e.model_dump() for e in game.events])
    except Exception:
        await db.games.update_one(
            {"_id": doc["_id"], "version": doc["version"] + 1},
            {"$set": {"state": doc["state"]}, "$inc": {"pending": -len(jobs)}},
        )
        raise
    doc["pending"] = doc.get("pending", 0) + len(jobs)
    tasks.add_task(commentary.write, doc["_id"], jobs, game.state.players)
    return view(doc, game.state, game.events)


@router.post("/games/{game_id}/advice")
async def advice(game_id: str, user: Annotated[User, Depends(current_user)]) -> GameView:
    doc = await load(game_id)
    if doc["owner"] != user.id:
        raise HTTPException(403, "Only the owner can ask for advice")
    state = State.model_validate(doc["state"])
    if state.turn.player != "p0" or state.turn.phase in ("attack", "over"):
        raise HTTPException(409, "Advice is for the start of your own move")
    now = state.turn.round
    if any(n["kind"] == "advice" and n["round"] == now for n in doc.get("notes", [])):
        return view(doc, state, [])
    try:
        note = await commentary.advise(Game(state))
    except Exception:
        raise HTTPException(503, "Your commanders are unavailable") from None
    await db.games.update_one(
        {"_id": doc["_id"], "notes": {"$not": {"$elemMatch": {"kind": "advice", "round": now}}}},
        {"$push": {"notes": note.model_dump()}},
    )
    doc = await load(game_id)
    return view(doc, State.model_validate(doc["state"]), [])


def apply(game: Game, command: Command) -> None:
    match command:
        case Reinforce():
            game.reinforce(command.country, command.soldiers)
        case Transfer():
            game.transfer(command.source, command.target, command.soldiers)
        case Attack():
            game.attack(command.source, command.target)
        case Simple(kind="roll"):
            game.roll()
        case Simple(kind="fight"):
            game.fight()
        case Simple(kind="stop"):
            game.stop()
        case Simple(kind="end_turn"):
            game.end_turn()


async def load(game_id: str) -> db.Document:
    valid = ObjectId.is_valid(game_id)
    doc = await db.games.find_one({"_id": ObjectId(game_id)}) if valid else None
    if doc is None:
        raise HTTPException(404, "No such game")
    return doc


def view(doc: db.Document, state: State, events: list[Event]) -> GameView:
    return GameView(
        id=str(doc["_id"]),
        owner=doc["owner"],
        state=state,
        events=events,
        notes=doc.get("notes", []),
        pending=doc.get("pending", 0),
    )
