"""The one strategy every NPC plays, with a stated reason for each decision."""

from math import comb
from typing import NamedTuple

from .engine import Country, Game, conquest_bonus


def win_probability(attackers: int, defenders: int) -> float:
    """Ties aside, each pair of dice is a coin flip costing one side a soldier, and an attack is
    settled within attackers + defenders - 2 flips. It wins if the defender loses enough of them.
    """
    flips = attackers + defenders - 2
    return sum(comb(flips, k) for k in range(defenders, flips + 1)) / (1 << flips)


class Option(NamedTuple):
    source: Country
    target: Country
    odds: float


def play_turn(game: Game) -> None:
    me = game.turn.player
    mine = game.countries_of(me)
    if game.turn.phase == "reinforce":
        army = max(mine, key=lambda c: c.soldiers)
        game.reinforce(
            army.code, game.turn.reinforcements, reason=f"{army.name} is its largest army."
        )

    options = [
        Option(s, t, win_probability(s.soldiers, t.soldiers))
        for s in mine
        if s.soldiers >= 2
        for t in game.state.countries
        if t.owner != me
    ]
    if not options:
        game.end_turn(reason="No country has the 2 soldiers needed to attack.")
        return
    viable = [o for o in options if o.odds >= 0.5]
    if not viable:
        best = max(options, key=lambda o: o.odds)
        game.end_turn(
            reason=f"The best option, {best.target.name} from {best.source.name}, "
            f"is only {best.odds:.0%} to succeed."
        )
        return

    source, target, odds = max(viable, key=lambda o: o.odds * conquest_bonus(o.target.value))
    game.attack(
        source.code,
        target.code,
        reason=f"{target.name} is the best target: {source.soldiers} vs {target.soldiers} "
        f"is {odds:.0%} to win {conquest_bonus(target.value)} soldiers.",
    )
    while game.turn.phase == "attack":
        odds = win_probability(source.soldiers, target.soldiers)
        if odds < 0.25:
            game.stop(
                reason=f"With {source.soldiers} soldiers left the chance of taking "
                f"{target.name} has dropped to {odds:.0%}."
            )
            return
        game.roll()
    if game.turn.phase == "over":
        return
    if target.owner == me and source.soldiers >= 2:
        game.transfer(
            source.code,
            target.code,
            source.soldiers // 2,
            reason=f"{target.name} needs more soldiers to hold.",
        )
    game.end_turn()


def run(game: Game) -> None:
    """Play NPC turns until it is the human's turn or the game is over."""
    while game.turn.phase != "over" and game.current_player.npc:
        play_turn(game)
