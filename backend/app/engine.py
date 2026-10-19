"""The rules of the game.

Pure Python with no web or database code. A `Game` wraps a `State`; every move either raises
`RuleError` or changes the state and appends `Event`s describing what changed. The browser never
applies rules: it shows the events in order, and each event carries the countries it changed and
the turn as it then stood.
"""

import random
from typing import Literal

from pydantic import BaseModel

DIE_SIDES = 6
REINFORCEMENTS_PER_COUNTRY = 2
COUNTRIES_PER_GAME = 10

Phase = Literal["reinforce", "action", "attack", "over"]
Kind = Literal[
    "started",
    "turn",
    "reinforced",
    "transferred",
    "attacked",
    "rolled",
    "conquered",
    "repelled",
    "stopped",
    "skipped",
    "eliminated",
    "over",
]
Pair = tuple[int, int]  # one attacking die against one defending die


class RuleError(Exception):
    """A move that the rules do not allow."""


class Player(BaseModel):
    id: str
    name: str
    npc: bool


class Country(BaseModel):
    code: str
    name: str
    value: int  # soldier value from its population; also sets the conquest bonus
    owner: str  # player id
    soldiers: int


class Attack(BaseModel):
    source: str  # country code
    target: str


class Turn(BaseModel):
    player: str
    round: int
    phase: Phase
    reinforcements: int = 0  # soldiers still to place this turn
    # This turn's one attack once launched; it is fought while the phase is "attack".
    attack: Attack | None = None
    winner: str | None = None  # set when the phase is "over"; None if the human was eliminated


class Event(BaseModel):
    seq: int
    kind: Kind
    text: str
    reason: str | None = None  # an NPC's justification for its decision
    dice: list[Pair] | None = None  # for "rolled": the pairs in the order they were matched
    countries: list[Country] = []  # countries whose owner or soldiers changed
    turn: Turn  # the turn as it stands after this event


class State(BaseModel):
    players: list[Player]  # in turn order
    countries: list[Country]
    turn: Turn
    seq: int = 0  # number of events logged so far


def conquest_bonus(value: int) -> int:
    """Soldiers gained for conquering a country: max(2, value / 2), rounded down."""
    return max(2, value // 2)


def dice_count(attacker_soldiers: int, defender_soldiers: int) -> int:
    """The attacker must leave one soldier behind; each die then meets one defending die."""
    return min(attacker_soldiers - 1, defender_soldiers)


class Game:
    def __init__(self, state: State, rng: random.Random | None = None) -> None:
        self.state = state
        self.events: list[Event] = []  # events produced since this object was created
        self.rng = rng or random.Random()

    @classmethod
    def new(cls, human: str, countries: list[Country], rng: random.Random | None = None) -> "Game":
        """Start a game: the human owns `countries[0]`, an NPC owns each other country."""
        if len(countries) != COUNTRIES_PER_GAME:
            raise RuleError(f"A game needs exactly {COUNTRIES_PER_GAME} countries")
        rng = rng or random.Random()
        players = [Player(id="p0", name=human, npc=False)]
        for i, country in enumerate(countries[1:], start=1):
            players.append(Player(id=f"p{i}", name=country.name, npc=True))
        for player, country in zip(players, countries, strict=True):
            country.owner = player.id
            country.soldiers = country.value
        rng.shuffle(players)  # the game randomly decides who goes first
        turn = Turn(player=players[0].id, round=1, phase="action")
        game = cls(State(players=players, countries=countries, turn=turn), rng)
        game._log("started", f"The game begins. {players[0].name} goes first.", countries)
        game._start_turn(players[0], 1)
        return game

    # -- reading -------------------------------------------------------------------------------

    @property
    def turn(self) -> Turn:
        return self.state.turn

    @property
    def current_player(self) -> Player:
        return self.player(self.turn.player)

    @property
    def human(self) -> Player:
        return next(p for p in self.state.players if not p.npc)

    def player(self, player_id: str) -> Player:
        return next(p for p in self.state.players if p.id == player_id)

    def country(self, code: str) -> Country:
        for country in self.state.countries:
            if country.code == code:
                return country
        raise RuleError(f"{code} is not part of this game")

    def countries_of(self, player_id: str) -> list[Country]:
        return [c for c in self.state.countries if c.owner == player_id]

    # -- moves ---------------------------------------------------------------------------------

    def reinforce(self, code: str, soldiers: int, reason: str | None = None) -> None:
        """Place some of this turn's new soldiers in one of your countries."""
        self._require("reinforce")
        country = self._own(code)
        if not 1 <= soldiers <= self.turn.reinforcements:
            raise RuleError(f"You have {self.turn.reinforcements} soldiers left to place")
        country.soldiers += soldiers
        self.turn.reinforcements -= soldiers
        if self.turn.reinforcements == 0:
            self.turn.phase = "action"
        self._log(
            "reinforced",
            f"{self.current_player.name} places {soldiers} soldiers in {country.name}.",
            [country],
            reason,
        )

    def transfer(self, source: str, target: str, soldiers: int, reason: str | None = None) -> None:
        """Move soldiers between two of your countries while no attack is in progress."""
        self._require("action")
        src, dst = self._own(source), self._own(target)
        if src is dst:
            raise RuleError("Choose two different countries")
        if soldiers < 1 or src.soldiers - soldiers < 1:
            raise RuleError(f"{src.name} must keep at least 1 soldier")
        src.soldiers -= soldiers
        dst.soldiers += soldiers
        self._log(
            "transferred",
            f"{self.current_player.name} moves {soldiers} soldiers from {src.name} to {dst.name}.",
            [src, dst],
            reason,
        )

    def attack(self, source: str, target: str, reason: str | None = None) -> None:
        """Launch the one attack of this turn."""
        self._require("action")
        if self.turn.attack is not None:
            raise RuleError("You can only attack once per turn")
        src, dst = self._own(source), self.country(target)
        if dst.owner == self.turn.player:
            raise RuleError("You cannot attack your own country")
        if src.soldiers < 2:
            raise RuleError("A country needs at least 2 soldiers to attack")
        self.turn.attack = Attack(source=source, target=target)
        self.turn.phase = "attack"
        self._log(
            "attacked",
            f"{src.name} attacks {dst.name}!",
            reason=reason,
        )

    def roll(self) -> None:
        """Roll one round of dice. Die 1 fights die 1, the higher roll wins, ties kill nobody."""
        self._require("attack")
        assert self.turn.attack is not None
        src, dst = self.country(self.turn.attack.source), self.country(self.turn.attack.target)
        pairs = [self._roll_pair() for _ in range(dice_count(src.soldiers, dst.soldiers))]
        attacker_lost = sum(a < d for a, d in pairs)
        defender_lost = sum(a > d for a, d in pairs)
        src.soldiers -= attacker_lost
        dst.soldiers -= defender_lost
        losses = [
            f"{c.name} loses {n}" for c, n in ((src, attacker_lost), (dst, defender_lost)) if n
        ]
        self._log(
            "rolled",
            f"{' and '.join(losses) or 'Every pair ties, nobody falls'}. "
            f"{src.name} has {src.soldiers} left, {dst.name} {dst.soldiers}.",
            [src, dst],
            dice=pairs,
        )
        if dst.soldiers == 0:
            self._conquer(src, dst)
        elif src.soldiers == 1:
            self.turn.phase = "action"
            self._log(
                "repelled", f"{src.name} is down to 1 soldier: the attack on {dst.name} fails."
            )

    def stop(self, reason: str | None = None) -> None:
        """Withdraw from the attack, which also ends the turn."""
        self._require("attack")
        assert self.turn.attack is not None
        target = self.country(self.turn.attack.target)
        self.turn.phase = "action"
        self._log(
            "stopped", f"{self.current_player.name} stops attacking {target.name}.", reason=reason
        )
        self.end_turn()

    def end_turn(self, reason: str | None = None) -> None:
        self._require("action")
        if self.turn.attack is None:
            self._log("skipped", f"{self.current_player.name} skips their attack.", reason=reason)
        self._next_turn()

    # -- internals -----------------------------------------------------------------------------

    def _require(self, phase: Phase) -> None:
        if self.turn.phase != phase:
            raise RuleError(f"Not allowed during the {self.turn.phase} phase")

    def _own(self, code: str) -> Country:
        country = self.country(code)
        if country.owner != self.turn.player:
            raise RuleError(f"{country.name} is not yours")
        return country

    def _roll_pair(self) -> Pair:
        return self.rng.randint(1, DIE_SIDES), self.rng.randint(1, DIE_SIDES)

    def _conquer(self, src: Country, dst: Country) -> None:
        loser = self.player(dst.owner)
        bonus = conquest_bonus(dst.value)
        dst.owner = self.turn.player
        dst.soldiers = bonus  # assumption: the bonus soldiers garrison the conquered country
        self.turn.phase = "action"
        self._log(
            "conquered",
            f"{self.current_player.name} conquers {dst.name} and gains {bonus} soldiers.",
            [dst],
        )
        eliminated = not self.countries_of(loser.id)
        if eliminated:
            self._log("eliminated", f"{loser.name} has no countries left and is out of the game.")
        if len(self.countries_of(self.turn.player)) == len(self.state.countries):
            self._end_game(self.current_player)
        elif eliminated and not loser.npc:
            self._end_game(None)

    def _end_game(self, winner: Player | None) -> None:
        self.turn.phase = "over"
        self.turn.winner = winner.id if winner else None
        text = f"{winner.name} has conquered the world!" if winner else "The NPCs rule the world."
        self._log("over", text)

    def _next_turn(self) -> None:
        players = self.state.players
        current = players.index(self.current_player)
        for step in range(1, len(players) + 1):
            index = (current + step) % len(players)
            if self.countries_of(players[index].id):  # eliminated players are skipped
                new_round = index <= current  # the order wrapped around
                self._start_turn(players[index], self.turn.round + new_round)
                return

    def _start_turn(self, player: Player, round: int) -> None:
        owned = len(self.countries_of(player.id))
        reinforcements = REINFORCEMENTS_PER_COUNTRY * owned if round > 1 else 0
        self.state.turn = Turn(
            player=player.id,
            round=round,
            phase="reinforce" if reinforcements else "action",
            reinforcements=reinforcements,
        )
        bonus = f" They receive {reinforcements} soldiers." if reinforcements else ""
        self._log("turn", f"Round {round}: {player.name}'s turn.{bonus}")

    def _log(
        self,
        kind: Kind,
        text: str,
        countries: list[Country] | None = None,
        reason: str | None = None,
        dice: list[Pair] | None = None,
    ) -> None:
        self.state.seq += 1
        self.events.append(
            Event(
                seq=self.state.seq,
                kind=kind,
                text=text,
                reason=reason,
                dice=dice,
                countries=[c.model_copy() for c in countries or []],
                turn=self.turn.model_copy(),
            )
        )
