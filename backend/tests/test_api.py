"""End-to-end checks through the HTTP API. They need a MongoDB at MONGO_URL (see compose.yaml)."""

import os
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pymongo import MongoClient
from pymongo.errors import PyMongoError

from app import db
from app.auth import hash_password, verify_password
from app.main import app

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
ANN = {"username": "ann", "password": "secret1"}
BOB = {"username": "bob", "password": "secret2"}


def test_password_hashes_verify_only_the_right_password() -> None:
    stored = hash_password("secret1")
    assert verify_password("secret1", stored)
    assert not verify_password("secret2", stored)
    assert hash_password("secret1") != stored  # a fresh salt every time


@pytest.fixture(scope="module")
def client() -> Iterator[TestClient]:
    mongo: MongoClient[dict[str, object]] = MongoClient(MONGO_URL, serverSelectionTimeoutMS=1000)
    try:
        mongo.drop_database("geopolitics_test")
    except PyMongoError:
        pytest.skip("MongoDB is not running")
    db.database = db.client["geopolitics_test"]
    db.users, db.sessions, db.games = (db.database[n] for n in ("users", "sessions", "games"))
    with TestClient(app) as test_client:
        yield test_client


def test_sign_up_log_in_and_log_out(client: TestClient) -> None:
    assert client.post("/api/auth/login", json=ANN).status_code == 401
    assert client.post("/api/auth/register", json=ANN).status_code == 200
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
    assert {k: za[k] for k in ("code", "name", "value", "owner")} == {
        "code": "ZA",
        "name": "South Africa",
        "value": 5,
        "owner": human["id"],
    }
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
    client.post("/api/auth/register", json=BOB)
    assert client.get("/api/games").json() == []
    assert client.get(f"/api/games/{game_id}").status_code == 200
    assert client.post(url, json={"kind": "end_turn"}).status_code == 403

    # A finished game takes no more commands.
    client.post("/api/auth/login", json=ANN)
    sync: MongoClient[dict[str, Any]] = MongoClient(MONGO_URL)
    sync["geopolitics_test"]["games"].update_one({}, {"$set": {"state.turn.phase": "over"}})
    assert client.post(url, json={"kind": "end_turn"}).status_code == 409
