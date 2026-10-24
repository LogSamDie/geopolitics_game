"""How the non-player characters play.

Every NPC uses the same strategy: put its reinforcements on its largest army, attack the target
with the best expected gain among those it has at least even odds against, withdraw from an
attack once the odds turn bad, and move half its army into a country it conquers. Every decision
carries a one-line justification for the game log.
"""

from math import comb
from typing import NamedTuple

from .engine import Country, Game, conquest_bonus

ATTACK_THRESHOLD = 0.5  # minimum chance of winning before an NPC launches an attack
STOP_THRESHOLD = 0.25  # an NPC withdraws once its chance of winning drops below this


def win_probability(attackers: int, defenders: int) -> float:
    """Chance that an attack fought to the end conquers the defender.

    Ties aside, every pair of dice is a coin flip that costs one side a soldier, and the attack
    is settled within attackers + defenders - 2 of them. It wins if the defender loses
    `defenders` of those flips.
    """
    flips = attackers + defenders - 2
    return sum(comb(flips, k) for k in range(defenders, flips + 1)) / (1 << flips)


class Option(NamedTuple):
    source: Country
    target: Country
    odds: float


def play_turn(game: Game) -> None:
    """Play the current NPC's whole turn."""
    me = game.turn.player
    mine = game.countries_of(me)
    if game.turn.phase == "reinforce":
        army = max(mine, key=lambda c: c.soldiers)
        game.reinforce(
            army.code,
            game.turn.reinforcements,
            reason=f"Reinforces {army.name}, its largest army, to attack with full strength.",
        )

    options = [
        Option(s, t, win_probability(s.soldiers, t.soldiers))
        for s in mine
        if s.soldiers >= 2
        for t in game.state.countries
        if t.owner != me
    ]
    viable = [o for o in options if o.odds >= ATTACK_THRESHOLD]
    if not viable:
        best = max(options, key=lambda o: o.odds, default=None)
        game.end_turn(
            reason=f"The best option, {best.target.name} from {best.source.name}, "
            f"is only {best.odds:.0%} to succeed."
            if best
            else "No country has the 2 soldiers needed to attack."
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
        if odds < STOP_THRESHOLD:
            game.stop(
                reason=f"With {source.soldiers} soldiers left the chance of taking "
                f"{target.name} has dropped to {odds:.0%}."
            )
            return
        game.roll()
    if game.turn.phase == "action":
        if target.owner == me and source.soldiers >= 2:
            game.transfer(
                source.code,
                target.code,
                source.soldiers // 2,
                reason=f"Garrisons {target.name} so it is not retaken at once.",
            )
        game.end_turn()


def run(game: Game) -> None:
    """Simulate NPC turns until it is the human's turn again or the game is over."""
    while game.turn.phase != "over" and game.current_player.npc:
        play_turn(game)
