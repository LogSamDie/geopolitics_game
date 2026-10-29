import pytest

from app.countries import COUNTRIES, soldier_value
from app.engine import RuleError, State, conquest_bonus
from tests.helpers import give_turn, human_turn, new_game, rig

# Soldiers from population


@pytest.mark.parametrize(
    ("population", "soldiers"),
    [
        (500, 1),  # Vatican City
        (5_000_000, 1),
        (5_000_001, 2),
        (10_000_000, 2),
        (10_000_001, 3),
        (25_000_000, 3),
        (25_000_001, 4),
        (50_000_000, 4),
        (50_000_001, 5),
        (75_000_000, 5),
        (75_000_001, 6),
        (100_000_000, 6),
        (100_000_001, 7),
        (125_000_000, 7),
        (125_000_001, 8),
        (150_000_000, 8),
        (150_000_001, 9),
        (1_476_625_576, 9),  # India
    ],
)
def test_soldier_value_follows_the_population_table(population: int, soldiers: int) -> None:
    assert soldier_value(population) == soldiers


def test_playable_countries_carry_their_value() -> None:
    assert COUNTRIES["IN"].value == 9
    assert COUNTRIES["ZA"].value == 5
    assert len(COUNTRIES) > 150


# Setup


def test_setup_gives_each_player_its_country_at_full_value() -> None:
    game = new_game()
    assert len(game.state.players) == 10
    assert game.human.name == "alice"
    [mine] = game.countries_of(game.human.id)
    assert (mine.code, mine.soldiers) == ("C0", 9)
    for player in game.state.players:
        [owned] = game.countries_of(player.id)
        assert owned.soldiers == owned.value
        assert player.npc == (player.name != "alice")
    assert [e.kind for e in game.events] == ["started", "turn"]
    assert len(game.events[0].countries) == 10
    assert game.turn.round == 1
    assert game.turn.phase == "action"  # no reinforcements in round 1


def test_the_first_player_is_random() -> None:
    assert len({new_game(seed=seed).turn.player for seed in range(10)}) > 1


# Rounds and reinforcements


def test_no_reinforcements_in_round_one() -> None:
    game = human_turn(new_game())
    assert game.turn.round == 1
    assert game.turn.reinforcements == 0
    assert all("receive" not in e.text for e in game.events if e.kind == "turn")


def test_two_soldiers_per_country_from_round_two() -> None:
    game = human_turn(new_game())
    for code in ("C1", "C2"):
        game.country(code).owner = game.human.id
    game.end_turn()
    human_turn(game)
    assert game.turn.round == 2
    assert game.turn.phase == "reinforce"
    assert game.turn.reinforcements == 6  # 3 countries
    assert game.events[-1].text.endswith("They receive 6 soldiers.")
    npc_turns = [
        e for e in game.events if e.kind == "turn" and e.turn.round == 2 and e.turn.player != "p0"
    ]
    assert all(e.turn.reinforcements == 2 for e in npc_turns)  # 1 country each


def test_reinforcements_may_be_split_but_must_all_be_placed_first() -> None:
    game = human_turn(new_game())
    game.country("C1").owner = game.human.id
    game.end_turn()
    human_turn(game)
    assert game.turn.reinforcements == 4
    with pytest.raises(RuleError, match="4 soldiers left"):
        game.reinforce("C0", 5)
    with pytest.raises(RuleError, match="4 soldiers left"):
        game.reinforce("C0", 0)
    with pytest.raises(RuleError, match="not yours"):
        game.reinforce("C2", 1)
    game.reinforce("C0", 3)
    assert game.turn.phase == "reinforce"
    assert game.turn.reinforcements == 1
    with pytest.raises(RuleError, match="reinforce phase"):
        game.end_turn()
    with pytest.raises(RuleError, match="reinforce phase"):
        game.attack("C0", "C2")
    with pytest.raises(RuleError, match="reinforce phase"):
        game.transfer("C0", "C1", 1)
    game.reinforce("C1", 1)
    assert game.state.turn.phase == "action"
    assert (game.country("C0").soldiers, game.country("C1").soldiers) == (12, 2)


def test_eliminated_players_are_skipped_for_the_rest_of_the_game() -> None:
    game = human_turn(new_game())
    game.country("C3").owner = game.human.id  # p3 has nothing left
    seen = []
    for _ in range(2 * 9):  # two laps of the nine remaining players
        if game.turn.phase == "reinforce":
            game.reinforce(game.countries_of(game.turn.player)[0].code, game.turn.reinforcements)
        game.end_turn()
        seen.append(game.turn.player)
    assert "p3" not in seen
    assert seen.count("p0") == 2
    assert game.turn.round == 3


# Transfers


def test_transfers_between_own_countries_keep_one_soldier_behind() -> None:
    game = human_turn(new_game())
    game.country("C1").owner = game.human.id
    with pytest.raises(RuleError, match="keep at least 1"):
        game.transfer("C0", "C1", 9)
    with pytest.raises(RuleError, match="keep at least 1"):
        game.transfer("C0", "C1", 0)
    with pytest.raises(RuleError, match="two different"):
        game.transfer("C0", "C0", 1)
    with pytest.raises(RuleError, match="not yours"):
        game.transfer("C0", "C2", 1)
    game.transfer("C0", "C1", 8)
    assert (game.country("C0").soldiers, game.country("C1").soldiers) == (1, 9)
    assert [c.code for c in game.events[-1].countries] == ["C0", "C1"]


def test_no_transfers_while_an_attack_is_in_progress() -> None:
    game = human_turn(new_game())
    game.country("C1").owner = game.human.id
    game.attack("C0", "C2")
    with pytest.raises(RuleError, match="attack phase"):
        game.transfer("C0", "C1", 1)
    rig(game, 6, 1)
    while game.turn.phase == "attack":
        game.roll()
    game.transfer("C0", "C2", 1)  # allowed again once the attack is over
    assert game.country("C2").soldiers == 3


# Attacking


def test_attack_needs_two_soldiers_an_own_source_and_an_enemy_target() -> None:
    game = human_turn(new_game())
    with pytest.raises(RuleError, match="not yours"):
        game.attack("C1", "C0")
    with pytest.raises(RuleError, match="your own"):
        game.attack("C0", "C0")
    with pytest.raises(RuleError, match="not part of this game"):
        game.attack("C0", "XX")
    game.country("C0").soldiers = 1
    with pytest.raises(RuleError, match="at least 2 soldiers"):
        game.attack("C0", "C1")
    with pytest.raises(RuleError, match="action phase"):
        game.roll()
    with pytest.raises(RuleError, match="action phase"):
        game.stop()


@pytest.mark.parametrize(
    ("attackers", "defenders", "dice"),
    [
        (10, 2, 2),
        (3, 5, 2),
        (2, 5, 1),
        (9, 9, 8),
    ],  # the spec's examples, plus the attacker's reserve
)
def test_dice_count_is_the_smaller_side_with_one_attacker_held_back(
    attackers: int, defenders: int, dice: int
) -> None:
    game = human_turn(new_game())
    game.country("C0").soldiers, game.country("C1").soldiers = attackers, defenders
    rig(game, 6)  # every pair ties, so the counts do not change
    game.attack("C0", "C1")
    game.roll()
    assert game.events[-1].dice == [(6, 6)] * dice


def test_dice_are_paired_in_order_and_the_higher_roll_wins() -> None:
    game = human_turn(new_game())
    src, dst = game.country("C0"), game.country("C1")
    src.soldiers, dst.soldiers = 10, 2
    rig(game, 1, 2, 4, 3)  # the spec's example: attacker 1 and 4, defender 2 and 3
    game.attack("C0", "C1")
    game.roll()
    assert game.events[-1].dice == [(1, 2), (4, 3)]
    assert (src.soldiers, dst.soldiers) == (9, 1)
    assert game.events[-1].text == "C0 loses 1 and C1 loses 1. C0 has 9 left, C1 1."
    assert game.turn.phase == "attack"


def test_fight_rolls_until_the_attack_ends() -> None:
    game = human_turn(new_game())
    game.country("C1").soldiers = 5
    rig(game, 3, 3, 6, 1)  # a tied pair, then a win, in turn
    game.attack("C0", "C1")
    game.fight()
    assert game.country("C1").owner == game.human.id
    kinds = [e.kind for e in game.events]
    assert kinds.count("rolled") >= 2
    assert kinds[-1] == "eliminated"
    assert game.turn.phase == "action"
    with pytest.raises(RuleError, match="action phase"):
        game.fight()


def test_a_tie_kills_nobody() -> None:
    game = human_turn(new_game())
    game.country("C1").soldiers = 3
    rig(game, 3)
    game.attack("C0", "C1")
    game.roll()
    assert (game.country("C0").soldiers, game.country("C1").soldiers) == (9, 3)
    assert game.events[-1].text.startswith("Every pair ties")


@pytest.mark.parametrize(("value", "bonus"), [(9, 4), (1, 2), (4, 2), (5, 2), (6, 3), (7, 3)])
def test_conquest_bonus_is_the_greater_of_two_and_half_the_value(value: int, bonus: int) -> None:
    assert conquest_bonus(value) == bonus


def test_conquest_garrisons_the_bonus_and_lets_the_turn_continue() -> None:
    game = human_turn(new_game())
    src, dst = game.country("C0"), game.country("C9")  # value 9: bonus 4
    rig(game, 6, 1)  # the attacker wins every pair
    game.attack("C0", "C9")
    while game.turn.phase == "attack":
        game.roll()
    assert (src.soldiers, dst.soldiers, dst.owner) == (9, 4, game.human.id)
    conquered = game.events[-2]
    assert conquered.kind == "conquered"
    assert [(c.code, c.owner, c.soldiers) for c in conquered.countries] == [("C9", "p0", 4)]
    assert conquered.turn.phase == "action"
    assert game.events[-1].kind == "eliminated"
    with pytest.raises(RuleError, match="once per turn"):
        game.attack("C0", "C1")
    game.transfer("C0", "C9", 5)  # soldiers may be moved into the new country
    game.end_turn()
    assert [e.kind for e in game.events[-2:]] == ["transferred", "turn"]  # no "skipped"


def test_attack_fails_when_the_attacker_is_down_to_one_soldier() -> None:
    game = human_turn(new_game())
    src, dst = game.country("C0"), game.country("C1")
    src.soldiers, dst.soldiers = 2, 5
    rig(game, 1, 6)  # the defender wins every pair
    game.attack("C0", "C1")
    game.roll()
    assert game.events[-1].kind == "repelled"
    assert (src.soldiers, src.owner, dst.soldiers, dst.owner) == (1, "p0", 5, "p1")
    assert game.turn.phase == "action"
    with pytest.raises(RuleError, match="once per turn"):
        game.attack("C0", "C1")
    game.end_turn()
    assert [e.kind for e in game.events[-2:]] == ["repelled", "turn"]


def test_stopping_an_attack_ends_the_turn_with_the_remaining_soldiers() -> None:
    game = human_turn(new_game())
    game.country("C1").soldiers = 4
    rig(game, 1, 6)
    game.attack("C0", "C1")
    game.roll()  # loses 4
    game.stop()
    assert game.country("C0").soldiers == 5
    assert [e.kind for e in game.events[-2:]] == ["stopped", "turn"]
    assert game.turn.player != game.human.id


# Winning and losing


def test_conquering_all_ten_countries_wins() -> None:
    game = human_turn(new_game())
    for c in game.state.countries[:-1]:
        c.owner = game.human.id
    last = game.state.countries[-1]
    rig(game, 6, 1)
    game.attack("C0", last.code)
    while game.turn.phase == "attack":
        game.roll()
    assert [e.kind for e in game.events[-3:]] == ["conquered", "eliminated", "over"]
    assert (game.turn.phase, game.turn.winner) == ("over", game.human.id)
    with pytest.raises(RuleError, match="over phase"):
        game.end_turn()


def test_an_npc_taking_the_human_last_country_to_complete_the_world_wins_once() -> None:
    game = new_game()
    for c in game.state.countries[1:]:
        c.owner = "p1"
    game.country("C0").soldiers = 1
    game.country("C1").soldiers = 10
    give_turn(game, "p1")
    rig(game, 6, 1)
    game.attack("C1", "C0")
    game.roll()
    assert [e.kind for e in game.events[-3:]] == ["conquered", "eliminated", "over"]
    assert game.turn.winner == "p1"
    assert game.events[-1].text == f"{game.player('p1').name} wins."
    assert [e.kind for e in game.events].count("over") == 1


def test_eliminating_an_npc_does_not_end_the_game() -> None:
    game = human_turn(new_game())
    rig(game, 6, 1)
    game.attack("C0", "C1")
    game.roll()
    assert [e.kind for e in game.events[-2:]] == ["conquered", "eliminated"]
    assert game.turn.phase == "action"
    assert not game.countries_of("p1")


# Events


def test_events_are_numbered_and_carry_independent_snapshots() -> None:
    game = human_turn(new_game())
    game.country("C1").soldiers = 10
    rig(game, 6, 1)
    game.attack("C0", "C1")
    game.roll()  # 8 dice: C1 is left with 2
    rolled = game.events[-1]
    assert [e.seq for e in game.events] == list(range(1, len(game.events) + 1))
    assert game.state.seq == len(game.events)
    assert [(c.code, c.soldiers) for c in rolled.countries] == [("C0", 9), ("C1", 2)]
    assert rolled.turn.phase == "attack"
    game.roll()  # conquers C1
    assert [(c.code, c.soldiers) for c in rolled.countries] == [("C0", 9), ("C1", 2)]
    assert rolled.turn.phase == "attack"


def test_state_round_trips_through_json() -> None:
    game = new_game()
    assert State.model_validate_json(game.state.model_dump_json()) == game.state
