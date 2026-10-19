"""Small builders shared by the tests."""

import random
from collections.abc import Sequence
from itertools import cycle

from app.engine import Country, Game, Phase

DEFAULT_VALUES = (9, 1, 2, 3, 4, 5, 6, 7, 8, 9)


def country(code: str, value: int) -> Country:
    return Country(code=code, name=code, value=value, owner="", soldiers=0)


def new_game(values: Sequence[int] = DEFAULT_VALUES, seed: int = 1) -> Game:
    """A game where the human "alice" (p0) owns C0 and NPC p<i> owns C<i>."""
    countries = [country(f"C{i}", v) for i, v in enumerate(values)]
    return Game.new("alice", countries, random.Random(seed))


def rig(game: Game, *values: int) -> None:
    """Make the dice show `values` in turn, repeating. Each pair rolls attacker then defender."""
    rolls = cycle(values)
    game.rng.randint = lambda a, b: next(rolls)  # type: ignore[method-assign]


def human_turn(game: Game) -> Game:
    """Pass the NPCs' turns without attacking until the human is to move."""
    while game.current_player.npc:
        if game.turn.phase == "reinforce":
            game.reinforce(game.countries_of(game.turn.player)[0].code, game.turn.reinforcements)
        game.end_turn()
    return game


def give_turn(game: Game, player_id: str, phase: Phase = "action") -> None:
    """Hand the turn to a player directly, bypassing the order."""
    game.state.turn.player = player_id
    game.state.turn.phase = phase
    game.state.turn.attack = None
