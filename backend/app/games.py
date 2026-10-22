"""Create games, read them (anyone with the link) and play a turn (the owner only).

A game document holds the current `state` plus the full `events` log. Every command loads the
state, applies the move, lets the NPCs play until it is the human's turn again, and saves both
the new state and the new events in one update guarded by a version number.
"""

import random
from datetime import UTC, datetime
from typing import Annotated, Literal

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from . import db, npc
from .auth import User, current_user
from .countries import COUNTRIES, CountryInfo
from .engine import COUNTRIES_PER_GAME, Country, Event, Game, RuleError, State, Turn

router = APIRouter(prefix="/api")
ALL_EVENTS = 10**6  # $slice needs an upper bound


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


class Roll(BaseModel):
    kind: Literal["roll"]


class Fight(BaseModel):
    kind: Literal["fight"]


class Stop(BaseModel):
    kind: Literal["stop"]


class EndTurn(BaseModel):
    kind: Literal["end_turn"]


Command = Annotated[
    Reinforce | Transfer | Attack | Roll | Fight | Stop | EndTurn, Field(discriminator="kind")
]


class NewGame(BaseModel):
    country: str  # the human's starting country


class GameSummary(BaseModel):
    id: str
    created: datetime
    human: str  # player id
    country: str  # the human's starting country
    turn: Turn
    countries: int  # held by the human


class GameView(BaseModel):
    id: str
    owner: str  # user id
    state: State
    events: list[Event]  # after the request's `after`, or produced by this request


@router.get("/countries")
def list_countries() -> list[CountryInfo]:
    return list(COUNTRIES.values())


@router.post("/games", status_code=201)
async def create_game(body: NewGame, user: Annotated[User, Depends(current_user)]) -> GameView:
    if body.country not in COUNTRIES:
        raise HTTPException(422, "Unknown country")
    others = [c for code, c in COUNTRIES.items() if code != body.country]
    chosen = [COUNTRIES[body.country], *random.sample(others, COUNTRIES_PER_GAME - 1)]
    countries = [
        Country(code=c.code, name=c.name, value=c.value, owner="", soldiers=0) for c in chosen
    ]
    game = Game.new(user.username, countries)
    npc.run(game)
    doc = {
        "owner": user.id,
        "created": datetime.now(UTC),
        "version": 1,
        "state": game.state.model_dump(),
        "events": [e.model_dump() for e in game.events],
    }
    doc["_id"] = (await db.games.insert_one(doc)).inserted_id
    return view(doc, game.state, game.events)


@router.get("/games")
async def list_games(user: Annotated[User, Depends(current_user)]) -> list[GameSummary]:
    summaries = []
    async for doc in db.games.find({"owner": user.id}, {"events": 0}).sort("created", -1):
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
async def get_game(game_id: str, after: Annotated[int, Query(ge=0, le=ALL_EVENTS)] = 0) -> GameView:
    """Anyone with the link may watch. Returns the events after sequence number `after`."""
    # events[i].seq == i + 1, so skipping `after` entries yields exactly the events after it.
    doc = await load(game_id, {"events": {"$slice": [after, ALL_EVENTS]}})
    events = [Event.model_validate(e) for e in doc["events"]]
    return view(doc, State.model_validate(doc["state"]), events)


@router.post("/games/{game_id}/commands")
async def play(
    game_id: str, command: Command, user: Annotated[User, Depends(current_user)]
) -> GameView:
    doc = await load(game_id, {"events": 0})
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
    result = await db.games.update_one(
        {"_id": doc["_id"], "version": doc["version"]},
        {
            "$set": {"state": game.state.model_dump()},
            "$push": {"events": {"$each": [e.model_dump() for e in game.events]}},
            "$inc": {"version": 1},
        },
    )
    if result.matched_count == 0:
        raise HTTPException(409, "The game changed in the meantime, reload it")
    return view(doc, game.state, game.events)


def apply(game: Game, command: Command) -> None:
    match command:
        case Reinforce():
            game.reinforce(command.country, command.soldiers)
        case Transfer():
            game.transfer(command.source, command.target, command.soldiers)
        case Attack():
            game.attack(command.source, command.target)
        case Roll():
            game.roll()
        case Fight():
            game.fight()
        case Stop():
            game.stop()
        case EndTurn():
            game.end_turn()


async def load(game_id: str, projection: db.Document) -> db.Document:
    query = {"_id": ObjectId(game_id)} if ObjectId.is_valid(game_id) else None
    doc = await db.games.find_one(query, projection) if query else None
    if doc is None:
        raise HTTPException(404, "No such game")
    return doc


def view(doc: db.Document, state: State, events: list[Event]) -> GameView:
    return GameView(id=str(doc["_id"]), owner=doc["owner"], state=state, events=events)
