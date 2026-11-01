import random

from app import npc
from tests.helpers import give_turn, new_game, rig


def simulate(attackers: int, defenders: int, rng: random.Random) -> bool:
    while defenders > 0 and attackers > 1:
        for _ in range(min(attackers - 1, defenders)):
            a, d = rng.randint(1, 6), rng.randint(1, 6)
            attackers -= a < d
            defenders -= a > d
    return defenders == 0


def test_win_probability_matches_simulation() -> None:
    rng = random.Random(7)
    for attackers, defenders in [(2, 1), (3, 2), (5, 5), (10, 2), (4, 8), (100, 90)]:
        wins = sum(simulate(attackers, defenders, rng) for _ in range(4000)) / 4000
        assert abs(npc.win_probability(attackers, defenders) - wins) < 0.03


def test_win_probability_edges() -> None:
    assert npc.win_probability(1, 5) == 0.0
    assert npc.win_probability(5, 0) == 1.0
    assert npc.win_probability(2, 1) == 0.5  # one die each, ties re-rolled
    assert npc.win_probability(3, 3) < npc.win_probability(4, 3) < npc.win_probability(5, 3)
    assert npc.win_probability(16, 15) == 0.5  # exactly even, so an NPC attacks
    assert npc.win_probability(1000, 10) > 0.99
    assert npc.win_probability(10, 1000) < 0.01


def test_npc_places_all_reinforcements_on_its_largest_army() -> None:
    game = new_game()
    game.country("C2").owner = "p1"
    give_turn(game, "p1", "reinforce")
    game.state.turn.reinforcements = 4
    game.country("C1").soldiers, game.country("C2").soldiers = 3, 1
    npc.play_turn(game)
    reinforced = next(e for e in game.events if e.kind == "reinforced")
    assert [(c.code, c.soldiers) for c in reinforced.countries] == [("C1", 7)]
    assert reinforced.reason is not None and "largest army" in reinforced.reason


def test_npc_attacks_the_target_with_the_best_expected_gain() -> None:
    game = new_game(values=[1, 9, 9, 1, 1, 1, 1, 1, 1, 1])  # C0 (human) and C3 are worth 1
    give_turn(game, "p1")
    game.country("C2").soldiers = 2  # worth 9: a slightly harder fight for a bonus of 4
    rig(game, 6, 1)
    npc.play_turn(game)
    attacked = next(e for e in game.events if e.kind == "attacked")
    assert attacked.turn.attack is not None and attacked.turn.attack.target == "C2"
    assert attacked.reason == "C2 is the best target: 9 vs 2 is 98% to win 4 soldiers."


def test_npc_prefers_a_viable_attack_over_a_richer_long_shot() -> None:
    game = new_game(values=[9, 3, 9, 1, 9, 9, 9, 9, 9, 9])
    give_turn(game, "p1")  # C1 has 3 soldiers
    game.country("C2").soldiers = 3  # worth 9 but only a 31% chance
    game.country("C3").soldiers = 2  # worth 1 with a 50% chance
    rig(game, 6, 1)
    npc.play_turn(game)
    attacked = next(e for e in game.events if e.kind == "attacked")
    assert attacked.turn.attack is not None and attacked.turn.attack.target == "C3"


def test_npc_moves_half_its_army_into_a_conquest() -> None:
    game = new_game(values=[9, 9, 1, 9, 9, 9, 9, 9, 9, 9])
    give_turn(game, "p1")
    rig(game, 6, 1)
    npc.play_turn(game)
    moved = game.events[-2]
    assert moved.kind == "transferred"
    assert moved.reason is not None and "to hold" in moved.reason
    assert [c.soldiers for c in moved.countries] == [5, 6]  # 9 - 4, and the bonus of 2 + 4


def test_games_against_a_passive_human_finish() -> None:
    for seed in range(40):
        rng = random.Random(seed)
        game = new_game([rng.randint(1, 9) for _ in range(10)], seed=seed)
        while game.turn.phase != "over" and game.turn.round < 500:
            npc.run(game)
            if game.turn.phase == "reinforce":
                game.reinforce(game.countries_of(game.human.id)[0].code, game.turn.reinforcements)
            if game.turn.phase == "action":
                game.end_turn()
        assert game.turn.phase == "over", f"seed {seed} still running at round 500"


def test_npc_skips_and_says_why_when_every_attack_is_a_long_shot() -> None:
    game = new_game(values=[9, 2, 9, 9, 9, 9, 9, 9, 9, 9])
    give_turn(game, "p1")
    npc.play_turn(game)
    skipped = game.events[-2]
    assert skipped.kind == "skipped"
    assert skipped.reason is not None and "is only" in skipped.reason
    assert game.turn.player != "p1"


def test_npc_skips_when_it_cannot_attack() -> None:
    game = new_game()
    give_turn(game, "p1")  # C1 has 1 soldier
    npc.play_turn(game)
    assert game.events[-2].reason == "No country has the 2 soldiers needed to attack."


def test_npc_withdraws_when_the_odds_drop() -> None:
    game = new_game(values=[3, 5, 3, 3, 3, 3, 3, 3, 3, 3])
    give_turn(game, "p1")  # 5 soldiers against 3 everywhere: a 66% chance, so it attacks
    rig(game, 1, 6)  # and loses every pair
    npc.play_turn(game)
    stopped = next(e for e in game.events if e.kind == "stopped")
    assert stopped.reason is not None and stopped.reason.startswith("With 2 soldiers left")
    assert game.country("C1").soldiers == 2
    assert game.turn.player != "p1"


def test_run_plays_every_npc_until_the_human_or_the_end() -> None:
    game = new_game()
    npc.run(game)
    assert not game.current_player.npc or game.turn.phase == "over"
    decisions = [e for e in game.events if e.kind in ("attacked", "skipped")]
    assert all(e.reason for e in decisions), "every NPC turn is justified"


def test_a_reckless_commander_attacks_where_a_cautious_one_does_not() -> None:
    for name, attacks in (("Admiral Atoll", True), ("Colonel Steppe", False)):
        game = new_game(values=[9, 3, 9, 9, 9, 9, 9, 9, 9, 9])
        game.player("p1").name = name
        give_turn(game, "p1")
        for country in game.state.countries[2:]:
            country.soldiers = 3
        game.country("C1").soldiers = 4  # 4 vs 3 is 50%
        rig(game, 6, 1)
        npc.play_turn(game)
        assert any(e.kind == "attacked" for e in game.events) == attacks
