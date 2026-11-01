"""Writing from DeepSeek, done after the moves are saved so no turn waits on it."""

import asyncio
import json
import os
import random
from collections import defaultdict
from itertools import groupby
from typing import Any, Literal

import httpx
from bson import ObjectId
from pydantic import BaseModel

from . import db
from .engine import PERSONALITIES, Event, Game, Player, conquest_bonus
from .npc import win_probability

SYSTEM_PROMPT = """You are the war correspondent of an imaginary world war, played as a board game \
between ten real countries. Write the chronicle of one battle, one line for each numbered event.

Make every battle a concrete scene in these actual places: their terrain, coasts, rivers, \
mountains, cities, climate, food and past. Invent how the armies got there, even across oceans, \
and what they do: a night crossing, a harbour landing, a mule train over a pass. Let history echo \
where it fits, such as old trade routes, empires or famous sieges. Carry on from the story so far.

Rules:
- Each line is one vivid sentence of at most 25 words, in plain, dry, confident prose.
- Every once in a while, the sentence can instead be funny/humorous yet must still make sense.
- Say who gained or lost ground, and follow the events exactly. Never contradict them.
- Always use neutral pronouns like "they", not "he" or "she".
- Never use a "—" unicode character or similar long em dashes.
- Never mention dice, rolls, turns, rounds, players, NPCs or that this is a game.
- Whoever an event names as acting is a fictional commander, however odd the name. Credit the \
right one by their full name, and name no real living person.
- Write a line for every event, in plain correct English.
- Keep it adventurous, not cruel: no real atrocities, no gore, and no group of people as the enemy.

Reply with JSON mapping each event number to its line, like this:
{"12": "Peruvian mule trains climb the Altiplano at dawn.", "13": "The first pass falls."}"""

LETTER_PROMPT = """You are a commander in an imaginary world war between real countries, writing a
short letter to your opponent right after a clash. Write 40 to 70 words, in character, that are
genuinely funny and surprising.
Build the letter on one specific idea: a real detail of these places (food, history, weather,
exports, famous oddities) turned into a petty complaint, a mock-formal demand, an absurd offer or a
running joke. Do not just gloat. No greeting or signature.
Use neutral pronouns. Never mention dice, rolls, turns, rounds or that this is a game.
Name no real living person. Never use a long em dash. No gore or cruelty.
If you have written to them before, carry on a running joke or grudge from those letters.
Reply with JSON like this: {"message": "Your letter."}"""

ADVICE_PROMPT = """You are the commanders advising a player in an imaginary world war between real
countries. Give 40 to 60 words of advice with dry humour: recommend one move from the options, say
why in terms of these actual places, and add one thing to watch out for. Never state odds or
percentages. Use neutral pronouns. Never use a long em dash. Never mention that this is a game.
Reply with JSON like this: {"advice": "Your advice."}"""

locks: defaultdict[ObjectId, asyncio.Lock] = defaultdict(asyncio.Lock)


class Note(BaseModel):
    seq: int  # the event it belongs to
    kind: Literal["line", "letter", "advice"]
    text: str
    player: str | None = None  # who sent a letter
    round: int | None = None  # of a letter or advice, as those are rationed


def jobs(game: Game) -> list[list[Event]]:
    """The battles to write about. Once the human is out, only those that knock someone out."""
    if not os.environ.get("DEEPSEEK_API_KEY"):
        return []
    narrated = ("attacked", "rolled", "conquered", "repelled", "stopped", "eliminated")
    events = [e for e in game.events if e.kind in narrated]
    battles = [
        list(group)
        for _, group in groupby(events, key=lambda e: (e.turn.player, e.turn.round, e.turn.attack))
    ]
    if not game.countries_of(game.human.id):
        return [b for b in battles if any(e.kind == "eliminated" for e in b)]
    return battles


async def ask(system: str, prompt: str, max_tokens: int, thinking: bool = False) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.post(
            "https://api.deepseek.com/chat/completions",
            headers={"Authorization": f"Bearer {os.environ['DEEPSEEK_API_KEY']}"},
            json={
                "model": "deepseek-flash",
                "thinking": {"type": "enabled" if thinking else "disabled"},
                "response_format": {"type": "json_object"},
                "max_tokens": max_tokens,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
            },
        )
    response.raise_for_status()
    return dict(json.loads(response.json()["choices"][0]["message"]["content"]))


def sender(battle: list[Event], players: list[Player]) -> Player | None:
    """The NPC with something to say after a country changed hands between them and the human."""
    rolled = next((e for e in battle if e.kind == "rolled"), None)
    if not rolled or not any(e.kind == "conquered" for e in battle):
        return None
    sides = {rolled.turn.player, rolled.countries[1].owner}  # from before the conquest
    npcs = [p for p in players if p.npc and p.id in sides]
    return npcs[0] if len(npcs) == 1 else None


def prompt_for(battle: list[Event], earlier: list[db.Document], story: list[str]) -> str:
    conquests = [e["text"] for e in earlier if e["kind"] in ("conquered", "eliminated")][-5:]
    sections = [
        "Earlier in the war:\n" + "\n".join(conquests) if conquests else "",
        "The story so far:\n" + "\n".join(story) if story else "",
        "This battle:\n" + "\n".join(f"{e.seq}: {e.text}" for e in battle),
    ]
    return "\n\n".join(s for s in sections if s)


async def write_lines(game_id: ObjectId, job: list[Event], notes: list[db.Document]) -> list[Note]:
    first = job[0].seq
    earlier = await db.load_events(game_id, first - 41, first)
    told = [n["text"] for n in notes if n["kind"] == "line"][-4:]
    reply = await ask(SYSTEM_PROMPT, prompt_for(job, earlier, told), 100 + 60 * len(job))
    return [
        Note(seq=e.seq, kind="line", text=str(reply[str(e.seq)]))
        for e in job
        if reply.get(str(e.seq))
    ]


async def write_letter(
    job: list[Event], players: list[Player], notes: list[db.Document]
) -> list[Note]:
    """A rare message: at most one every three rounds, unless someone is knocked out."""
    speaker = sender(job, players)
    if not speaker:
        return []
    now = job[-1].turn.round
    letters = [n for n in notes if n["kind"] == "letter"]
    if not any(e.kind == "eliminated" for e in job) and any(n["round"] > now - 3 for n in letters):
        return []
    human = next(p for p in players if not p.npc)
    prompt = (
        f"You are {speaker.name}: {PERSONALITIES[speaker.name].voice}. "
        f"You are writing to {human.name}.\n\nWhat happened:\n" + "\n".join(e.text for e in job)
    )
    sent = [n["text"] for n in letters if n["player"] == speaker.id][-3:]
    if sent:
        prompt += "\n\nYour earlier letters to them:\n" + "\n".join(sent)
    reply = await ask(LETTER_PROMPT, prompt, 3000, thinking=True)
    return [
        Note(
            seq=job[-1].seq,
            kind="letter",
            text=str(reply["message"]),
            player=speaker.id,
            round=now,
        )
    ]


async def write(game_id: ObjectId, game_jobs: list[list[Event]], players: list[Player]) -> None:
    """In order, also across moves, so that each piece can follow on from the last."""
    async with locks[game_id]:
        for job in game_jobs:
            try:
                doc = await db.games.find_one({"_id": game_id}, {"notes": 1})
                assert doc is not None
                notes = doc.get("notes", [])
                await keep(game_id, await write_lines(game_id, job, notes))
                await keep(game_id, await write_letter(job, players, notes))
            except Exception as error:  # this is a bonus: a failure must not stop the game
                print(f"Nothing written for event {job[0].seq}: {error!r}")
            await db.games.update_one({"_id": game_id}, {"$inc": {"pending": -1}})


async def keep(game_id: ObjectId, notes: list[Note]) -> None:
    await db.games.update_one(
        {"_id": game_id}, {"$push": {"notes": {"$each": [n.model_dump() for n in notes]}}}
    )


def board(game: Game, sound: bool) -> str:
    """What the advisors know. Exact odds rank the options, but they never see the numbers."""
    me = game.human.id
    extra = game.turn.reinforcements
    mine = game.countries_of(me)
    enemies = [c for c in game.state.countries if c.owner != me]
    lines = [
        "You hold: " + ", ".join(f"{c.name} {c.soldiers}" for c in mine),
        "Enemies: "
        + ", ".join(
            f"{c.name} {c.soldiers} ({game.player(c.owner).name}: "
            f"{PERSONALITIES[game.player(c.owner).name].voice})"
            for c in enemies
        ),
    ]
    if extra:
        lines.append(f"You must place {extra} new soldiers first.")
    if game.turn.attack:
        lines.append(
            "You have already attacked this turn, "
            "so advise on moving soldiers, or on ending the turn if none can move."
        )
    else:
        options = [(s, t) for s in mine if s.soldiers + extra >= 2 for t in enemies]
        options.sort(
            key=lambda o: (
                win_probability(o[0].soldiers + extra, o[1].soldiers) * conquest_bonus(o[1].value)
            ),
            reverse=sound,
        )
        lines += [f"Attack {t.name} from {s.name}" for s, t in options[:4]] or [
            "No attack is possible."
        ]
    lines.append(
        "Recommend the first option."
        if sound
        else "Today you are confidently and hilariously wrong. Recommend the first option as if it "
        "were genius, with reasons that sound convincing and make no sense. Never hint it is bad."
    )
    return "\n".join(lines)


async def advise(game: Game) -> Note:
    reply = await ask(ADVICE_PROMPT, board(game, sound=random.random() > 0.25), 3000, thinking=True)
    return Note(seq=game.state.seq, kind="advice", text=str(reply["advice"]), round=game.turn.round)
