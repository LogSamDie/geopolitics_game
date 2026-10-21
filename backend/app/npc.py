"""How the non-player characters play.

Every NPC uses the same strategy: put its reinforcements on its largest army, attack the target
with the best expected gain among those it has at least even odds against, and withdraw from an
attack once the odds turn bad. Every decision carries a one-line justification for the game log.
"""

from functools import cache
from math import comb
from typing import NamedTuple

from .engine import DIE_SIDES, Country, Game, conquest_bonus, dice_count

ATTACK_THRESHOLD = 0.5  # minimum chance of winning before an NPC launches an attack
STOP_THRESHOLD = 0.25  # an NPC withdraws once its chance of winning drops below this
MAX_ARMY = 40  # larger armies are scaled down before computing odds, keeping the table small

FACES = range(1, DIE_SIDES + 1)
P_LOSE = sum(a < d for a in FACES for d in FACES) / DIE_SIDES**2  # chance one side loses a pair
P_TIE = 1 - 2 * P_LOSE


@cache
def win_probability(attackers: int, defenders: int) -> float:
    """Chance that an attack fought to the end conquers the defender.

    Exact for armies up to MAX_ARMY; larger ones are scaled down proportionally, which keeps the
    balance of forces while bounding the recursion. Rounds where every pair ties leave the state
    unchanged, which the division at the end accounts for.
    """
    if defenders == 0:
        return 1.0
    if attackers < 2:
        return 0.0
    scale = max(attackers, defenders) / MAX_ARMY
    if scale > 1:
        return win_probability(max(2, round(attackers / scale)), max(1, round(defenders / scale)))
    n = dice_count(attackers, defenders)
    total = 0.0
    for lost_a in range(n + 1):
        for lost_d in range(n + 1 - lost_a):
            ties = n - lost_a - lost_d
            if ties == n:
                continue
            p = (
                comb(n, lost_a)
                * comb(n - lost_a, lost_d)
                * P_LOSE ** (lost_a + lost_d)
                * P_TIE**ties
            )
            total += p * win_probability(attackers - lost_a, defenders - lost_d)
    return total / (1 - P_TIE**n)


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
        f"soldiers is {odds:.0%} to win {conquest_bonus(target.value)} soldiers.",
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
        game.end_turn()


def run(game: Game) -> None:
    """Simulate NPC turns until it is the human's turn again or the game is over."""
    while game.turn.phase != "over" and game.current_player.npc:
        play_turn(game)
