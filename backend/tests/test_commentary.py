import asyncio
from unittest.mock import AsyncMock

import pytest

from app import commentary, npc
from app.engine import Game
from tests.helpers import give_turn, human_turn, new_game, rig


@pytest.fixture(autouse=True)
def api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test")


def won_battle() -> Game:
    """The human has just conquered C1, which knocks out p1. Only that battle's events are left."""
    game = human_turn(new_game())
    game.events.clear()
    rig(game, 6, 1)
    game.attack("C0", "C1")
    game.fight()
    return game


def test_no_key_means_no_jobs(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DEEPSEEK_API_KEY")
    game = human_turn(new_game())
    game.attack("C0", "C1")
    assert commentary.jobs(game) == []


def test_a_battle_is_one_job_of_only_its_narrated_events() -> None:
    [battle] = commentary.jobs(won_battle())
    assert battle[0].kind == "attacked"
    assert battle[-1].kind == "eliminated"


def test_separate_battles_are_separate_jobs() -> None:
    game = new_game(values=[9, 9, 9, 1, 1, 1, 1, 1, 1, 1])
    game.events.clear()
    for player in ("p1", "p2"):
        give_turn(game, player)
        rig(game, 6, 1)
        npc.play_turn(game)
    assert len([j for j in commentary.jobs(game) if j[0].kind == "attacked"]) == 2


def test_once_the_human_is_out_only_deciding_battles_are_narrated() -> None:
    game = new_game()
    game.country("C0").soldiers, game.country("C1").soldiers = 1, 10
    give_turn(game, "p1")
    rig(game, 6, 1)
    game.events.clear()
    game.attack("C1", "C0")
    game.roll()
    game.end_turn()
    give_turn(game, "p2")
    game.country("C2").soldiers, game.country("C3").soldiers = 5, 5
    rig(game, 3, 3, 6, 1)
    game.attack("C2", "C3")
    game.roll()
    kinds = [[e.kind for e in job] for job in commentary.jobs(game)]
    assert len(kinds) == 1
    assert "eliminated" in kinds[0]


def test_the_npc_only_speaks_up_once_a_country_changes_hands() -> None:
    game = human_turn(new_game())
    game.events.clear()
    game.country("C1").soldiers = 9
    rig(game, 3)  # ties, so the battle goes on
    game.attack("C0", "C1")
    game.roll()
    players = game.state.players
    assert commentary.sender(game.events, players) is None
    rig(game, 6, 1)
    game.fight()
    speaker = commentary.sender(game.events, players)
    assert speaker is not None and speaker.id == "p1"


def test_npcs_fighting_each_other_do_not_write() -> None:
    game = new_game()
    give_turn(game, "p1")
    game.country("C1").soldiers = 9
    rig(game, 6, 1)
    game.events.clear()
    game.attack("C1", "C2")
    game.fight()
    assert commentary.sender(game.events, game.state.players) is None


def test_the_battle_prompt_holds_only_a_little_history() -> None:
    game = human_turn(new_game())
    game.attack("C0", "C1")
    battle = game.events[-1:]
    earlier = [{"kind": "conquered", "text": f"Conquest {i}"} for i in range(9)] + [
        {"kind": "rolled", "text": "A roll"}
    ]
    prompt = commentary.prompt_for(battle, earlier, ["A line of the story."])
    assert f"{battle[0].seq}: {battle[0].text}" in prompt
    assert "Conquest 8" in prompt and "Conquest 3" not in prompt
    assert "A roll" not in prompt
    assert "A line of the story." in prompt
    assert "json" in commentary.SYSTEM_PROMPT.lower()


def test_the_advisor_gets_exact_odds_and_knows_when_the_attack_is_used() -> None:
    game = human_turn(new_game())
    board = commentary.board(game)
    assert "to win" in board and "%" in board
    rig(game, 6, 1)
    game.attack("C0", "C1")
    game.fight()
    assert "already attacked" in commentary.board(game)


@pytest.mark.parametrize(
    ("last_round", "knocked_out", "speaks"),
    [(None, False, True), (2, False, False), (1, False, True), (2, True, True)],
)
def test_messages_are_rare_unless_someone_is_knocked_out(
    monkeypatch: pytest.MonkeyPatch, last_round: int | None, knocked_out: bool, speaks: bool
) -> None:
    game = won_battle()
    game.turn.round = 4
    job = [e.model_copy(update={"turn": game.turn}) for e in game.events]
    if not knocked_out:
        job = [e for e in job if e.kind != "eliminated"]
    letters = (
        []
        if last_round is None
        else [{"kind": "letter", "round": last_round, "player": "p1", "text": "Earlier."}]
    )

    ask = AsyncMock(return_value={"message": "So there."})
    monkeypatch.setattr(commentary, "ask", ask)
    notes = asyncio.run(commentary.write_letter(job, game.state.players, letters))
    assert bool(notes) == speaks
    if speaks:
        assert notes[0].player == "p1" and notes[0].round == 4
        assert ask.call_args.kwargs == {"thinking": True}


def test_a_commander_remembers_only_their_own_letters(monkeypatch: pytest.MonkeyPatch) -> None:
    game = won_battle()
    letters = [
        {"kind": "letter", "player": "p1", "round": -9, "text": "My own joke."},
        {"kind": "letter", "player": "p2", "round": -9, "text": "Someone else's."},
    ]
    ask = AsyncMock(return_value={"message": "So there."})
    monkeypatch.setattr(commentary, "ask", ask)
    asyncio.run(commentary.write_letter(game.events, game.state.players, letters))
    prompt = ask.call_args.args[1]
    assert "My own joke." in prompt and "Someone else's." not in prompt
