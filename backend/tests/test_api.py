"""End-to-end checks through the HTTP API. They need a MongoDB at MONGO_URL (see compose.yaml)."""

import os
from collections.abc import Iterator
from typing import Any
from unittest.mock import AsyncMock

import httpx
import pytest
from bson import ObjectId
from fastapi.testclient import TestClient
from pymongo import MongoClient
from pymongo.errors import PyMongoError

from app import commentary, db
from app.auth import hash_password, verify_password
from app.main import app

MONGO: MongoClient[dict[str, Any]] = MongoClient(
    os.environ.get("MONGO_URL", "mongodb://localhost:27017"), serverSelectionTimeoutMS=1000
)
ANN = {"username": "ann", "password": "secret1"}


def test_password_hashes_verify_only_the_right_password() -> None:
    stored = hash_password("secret1")
    assert verify_password("secret1", stored)
    assert not verify_password("secret2", stored)
    assert hash_password("secret1") != stored  # a fresh salt every time


@pytest.fixture(autouse=True)
def no_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)


@pytest.fixture(scope="module")
def client() -> Iterator[TestClient]:
    try:
        MONGO.drop_database("geopolitics_test")
    except PyMongoError:
        pytest.skip("MongoDB is not running")
    db.database = db.client["geopolitics_test"]
    db.users, db.sessions, db.games, db.events = (
        db.database[n] for n in ("users", "sessions", "games", "events")
    )
    with TestClient(app, base_url="https://testserver") as test_client:
        yield test_client


def test_sign_up_log_in_and_log_out(client: TestClient) -> None:
    assert client.post("/api/auth/login", json=ANN).status_code == 401
    registered = client.post("/api/auth/register", json=ANN)
    assert registered.status_code == 200
    assert "secure" in registered.headers["set-cookie"].lower()
    assert client.post("/api/auth/register", json=ANN).status_code == 409
    assert (
        client.post("/api/auth/register", json={"username": "a b", "password": "x"}).status_code
        == 422
    )
    assert client.get("/api/auth/me").json()["username"] == "ann"

    token = client.cookies["session"]
    assert client.post("/api/auth/logout").status_code == 204
    assert client.get("/api/auth/me").status_code == 401
    client.cookies.set("session", token)
    assert client.get("/api/auth/me").status_code == 401, "logging out invalidates the session"
    client.cookies.clear()

    assert client.post("/api/auth/login", json={**ANN, "password": "wrong1"}).status_code == 401
    assert client.post("/api/auth/login", json=ANN).json()["username"] == "ann"
    assert client.get("/api/auth/me").status_code == 200


def test_play_a_game_through_the_api(client: TestClient) -> None:
    countries = client.get("/api/countries").json()
    assert next(c for c in countries if c["code"] == "IN")["value"] == 9

    assert client.post("/api/games", json={"country": "XX"}).status_code == 422
    created = client.post("/api/games", json={"country": "ZA"})
    assert created.status_code == 201
    game_id = created.json()["id"]
    state = created.json()["state"]
    human = next(p for p in state["players"] if not p["npc"])
    assert human["name"] == "ann"
    za = state["countries"][0]
    assert (za["code"], za["name"], za["value"]) == ("ZA", "South Africa", 5)
    assert za["owner"] == human["id"]
    assert 1 <= za["soldiers"] <= 5  # the NPCs may have attacked it already
    assert state["turn"]["player"] == human["id"], "NPC turns ran before responding"

    [summary] = client.get("/api/games").json()
    assert (summary["id"], summary["country"], summary["countries"]) == (game_id, "South Africa", 1)

    view = client.get(f"/api/games/{game_id}").json()
    assert view["events"][0]["kind"] == "started"
    seq = view["events"][-1]["seq"]
    assert client.get(f"/api/games/{game_id}?after={seq}").json()["events"] == []
    assert client.get("/api/games/000000000000000000000000").status_code == 404
    assert client.get("/api/games/not-an-id").status_code == 404

    url = f"/api/games/{game_id}/commands"
    assert client.post(url, json={"kind": "roll"}).status_code == 422  # not attacking
    assert client.post(url, json={"kind": "bogus"}).status_code == 422
    assert client.post(url, json={"kind": "fight"}).status_code == 422  # not attacking
    assert (
        client.post(url, json={"kind": "attack", "source": "ZA", "target": "ZA"}).status_code == 422
    )

    # Round 1: skip. Round 2 arrives with reinforcements that must be placed first.
    turn = client.post(url, json={"kind": "end_turn"}).json()
    assert turn["events"][0]["kind"] == "skipped"
    assert turn["events"][0]["seq"] == seq + 1
    assert turn["state"]["turn"]["phase"] in ("reinforce", "over")
    if turn["state"]["turn"]["phase"] == "over":
        pytest.skip("the NPCs eliminated ann in round 1")
    mine = [c for c in turn["state"]["countries"] if c["owner"] == human["id"]]
    assert turn["state"]["turn"]["reinforcements"] == 2 * len(mine)
    assert (
        client.post(url, json={"kind": "attack", "source": "ZA", "target": "XX"}).status_code == 422
    )
    placed = client.post(
        url, json={"kind": "reinforce", "country": mine[0]["code"], "soldiers": 2 * len(mine)}
    ).json()
    assert placed["events"][0]["kind"] == "reinforced"
    assert placed["state"]["turn"]["phase"] == "action"

    # Attack, roll once, then stop: stopping ends the turn.
    enemy = next(c for c in placed["state"]["countries"] if c["owner"] != human["id"])
    attack = client.post(
        url, json={"kind": "attack", "source": mine[0]["code"], "target": enemy["code"]}
    ).json()
    assert attack["events"][0]["kind"] == "attacked"
    rolled = client.post(url, json={"kind": "roll"}).json()
    assert rolled["events"][0]["kind"] == "rolled"
    assert rolled["events"][0]["dice"]
    if rolled["state"]["turn"]["phase"] == "attack":
        stopped = client.post(url, json={"kind": "stop"}).json()
        assert [e["kind"] for e in stopped["events"][:2]] == ["stopped", "turn"]

    # Nobody else may play it: not a visitor, not another user. Both may watch.
    client.post("/api/auth/logout")
    assert client.get(f"/api/games/{game_id}").status_code == 200
    assert client.post(url, json={"kind": "end_turn"}).status_code == 401
    client.post("/api/auth/register", json={"username": "bob", "password": "secret2"})
    assert client.get("/api/games").json() == []
    assert client.get(f"/api/games/{game_id}").status_code == 200
    assert client.post(url, json={"kind": "end_turn"}).status_code == 403

    # A finished game takes no more commands.
    client.post("/api/auth/login", json=ANN)
    MONGO["geopolitics_test"]["games"].update_one({}, {"$set": {"state.turn.phase": "over"}})
    assert client.post(url, json={"kind": "end_turn"}).status_code == 409


def start_game(client: TestClient, username: str, country: str) -> dict[str, Any]:
    """Sign up a new player and start their game, which the NPCs may end before they move."""
    client.post("/api/auth/register", json={"username": username, "password": "secret1"})
    game: dict[str, Any] = client.post("/api/games", json={"country": country}).json()
    if game["state"]["turn"]["phase"] == "over":
        pytest.skip("the NPCs finished this game before the human moved")
    return game


def test_writing_happens_after_a_move_and_failures_do_not_stick(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test")
    prompts = []

    async def fake_ask(system: str, prompt: str, *args: object, **kwargs: object) -> dict[str, Any]:
        prompts.append(prompt)
        if "This battle:" not in prompt:
            return {"message": "So there."}
        seqs = [line.split(":")[0] for line in prompt.split("This battle:")[1].split()]
        return {seq: f"Line {seq}" for seq in seqs if seq.isdigit()} | {"999999": "made up"}

    monkeypatch.setattr(commentary, "ask", fake_ask)
    game = start_game(client, "cam", "CN")
    url = f"/api/games/{game['id']}"
    enemy = next(c for c in game["state"]["countries"] if c["owner"] != "p0")
    client.post(f"{url}/commands", json={"kind": "attack", "source": "CN", "target": enemy["code"]})
    view = client.get(url).json()
    assert view["pending"] == 0
    assert 999999 not in [n["seq"] for n in view["notes"]]
    attacked = next(
        e for e in view["events"] if e["turn"]["player"] == "p0" and e["kind"] == "attacked"
    )
    assert {
        "seq": attacked["seq"],
        "kind": "line",
        "text": f"Line {attacked['seq']}",
        "player": None,
        "round": None,
    } in view["notes"]

    for prompt in prompts:
        if "Earlier in the war:" in prompt:
            first = int(prompt.split("This battle:\n")[1].split(":")[0])
            earlier = prompt.split("Earlier in the war:\n")[1].split("\n\n")[0].split("\n")
            known = {e["text"] for e in view["events"] if e["seq"] < first}
            assert set(earlier) <= known, "a battle must not be told about its own future"

    monkeypatch.setattr(commentary, "ask", AsyncMock(side_effect=httpx.ConnectError("down")))
    assert client.post(f"{url}/commands", json={"kind": "roll"}).status_code == 200
    assert client.get(url).json()["pending"] == 0


def test_advice_is_for_the_owner_and_once_per_round(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    ask = AsyncMock(return_value={"advice": "Attack."})
    monkeypatch.setattr(commentary, "ask", ask)
    game = start_game(client, "dee", "IN")
    url = f"/api/games/{game['id']}/advice"
    first = client.post(url).json()
    assert [n["text"] for n in first["notes"] if n["kind"] == "advice"] == ["Attack."]
    enemy = next(c for c in game["state"]["countries"] if c["owner"] != "p0")
    commands = f"/api/games/{game['id']}/commands"
    client.post(commands, json={"kind": "attack", "source": "IN", "target": enemy["code"]})
    client.post(commands, json={"kind": "fight"})
    client.post(url)
    ask.assert_awaited_once()
    assert ask.call_args.kwargs["thinking"] is True

    client.post("/api/auth/logout")
    assert client.post(url).status_code == 401
    client.post("/api/auth/register", json={"username": "eve", "password": "secret5"})
    assert client.post(url).status_code == 403


def test_events_come_back_in_order_across_moves_from_any_point(client: TestClient) -> None:
    game = start_game(client, "fay", "PE")
    url = f"/api/games/{game['id']}"
    moved = client.post(f"{url}/commands", json={"kind": "end_turn"}).json()
    events = client.get(url).json()["events"]
    seqs = [e["seq"] for e in events]
    assert seqs == list(range(1, len(seqs) + 1))
    assert events[-len(moved["events"]) :] == moved["events"]
    middle = seqs[len(seqs) // 2]
    assert client.get(f"{url}?after={middle}").json()["events"] == events[middle:]
    stored = MONGO["geopolitics_test"]["games"].find_one({"_id": ObjectId(game["id"])})
    assert stored is not None and "events" not in stored


def test_a_move_whose_events_cannot_be_saved_is_undone(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    game = start_game(client, "gus", "NO")
    url = f"/api/games/{game['id']}"
    with monkeypatch.context() as patch:
        patch.setattr(db, "save_events", AsyncMock(side_effect=PyMongoError("down")))
        with pytest.raises(PyMongoError):
            client.post(f"{url}/commands", json={"kind": "end_turn"})
    assert client.get(url).json()["state"] == game["state"]
    assert client.post(f"{url}/commands", json={"kind": "end_turn"}).status_code == 200
