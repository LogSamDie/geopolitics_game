"""The rules of the game: every move raises RuleError or changes the state and logs events."""

import random
from typing import Literal, NamedTuple

from pydantic import BaseModel


class Personality(NamedTuple):
    voice: str
    attack_odds: float  # the least chance of winning it starts an attack with
    stop_odds: float  # it withdraws below this
    garrison: float  # the share of the army it moves into a conquest


PERSONALITIES = {
    "Marshal Tundra": Personality("pompous, quotes their own memoirs", 0.5, 0.25, 0.5),
    "General Isthmus": Personality("weary bureaucrat, cites regulations", 0.5, 0.25, 0.5),
    "Admiral Atoll": Personality("reckless sea dog, loves a gamble", 0.35, 0.15, 0.25),
    "Colonel Steppe": Personality("cautious and gloomy, expects the worst", 0.65, 0.4, 0.75),
    "Baroness Delta": Personality("haughty aristocrat, finds war vulgar", 0.35, 0.15, 0.25),
    "President Mesa": Personality("slippery politician, always campaigning", 0.65, 0.4, 0.75),
    "Commodore Fjord": Personality("laconic, says as little as possible", 0.65, 0.4, 0.75),
    "Chancellor Savanna": Personality("cheerfully menacing, loves a metaphor", 0.35, 0.15, 0.25),
    "Generalissimo Oasis": Personality(
        "vain, refers to themselves in the third person", 0.5, 0.25, 0.5
    ),
}

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


class RuleError(Exception):
    pass


class Player(BaseModel):
    id: str
    name: str
    npc: bool


class Country(BaseModel):
    code: str
    name: str
    value: int  # soldiers it starts with, from its population
    owner: str = ""  # player id
    soldiers: int = 0


class Attack(BaseModel):
    source: str
    target: str


class Turn(BaseModel):
    player: str
    round: int
    phase: Phase
    reinforcements: int = 0  # still to place
    attack: Attack | None = None  # stays set after the attack ends, so it happens once a turn
    winner: str | None = None


class Event(BaseModel):
    seq: int
    kind: Kind
    text: str
    reason: str | None = None  # why an NPC did this
    dice: list[tuple[int, int]] | None = None  # (attacker, defender) pairs
    countries: list[Country] = []  # those this event changed
    turn: Turn  # as it stands after this event


class State(BaseModel):
    players: list[Player]  # in turn order
    countries: list[Country]
    turn: Turn
    seq: int = 0  # events logged so far


def soldiers(n: int) -> str:
    return f"{n} soldier{'' if n == 1 else 's'}"


def conquest_bonus(value: int) -> int:
    return max(2, value // 2)


class Game:
    def __init__(self, state: State, rng: random.Random | None = None) -> None:
        self.state = state
        self.events: list[Event] = []  # logged since this object was created
        self.rng = rng or random.Random()

    @classmethod
    def new(cls, human: str, countries: list[Country], rng: random.Random | None = None) -> "Game":
        """The human (p0) owns the first country, an NPC each of the others."""
        rng = rng or random.Random()
        players = [Player(id="p0", name=human, npc=False)]
        for i, name in enumerate(PERSONALITIES, start=1):
            players.append(Player(id=f"p{i}", name=name, npc=True))
        for player, country in zip(players, countries, strict=True):
            country.owner = player.id
            country.soldiers = country.value
        rng.shuffle(players)
        turn = Turn(player=players[0].id, round=1, phase="action")
        game = cls(State(players=players, countries=countries, turn=turn), rng)
        game._log("started", f"{players[0].name} goes first.", countries)
        game._start_turn(players[0], 1)
        return game

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

    def reinforce(self, code: str, count: int, reason: str | None = None) -> None:
        self._require("reinforce")
        country = self._own(code)
        if not 1 <= count <= self.turn.reinforcements:
            raise RuleError(f"You have {self.turn.reinforcements} soldiers left to place")
        country.soldiers += count
        self.turn.reinforcements -= count
        if self.turn.reinforcements == 0:
            self.turn.phase = "action"
        self._log(
            "reinforced",
            f"{self.current_player.name} places {soldiers(count)} in {country.name}.",
            [country],
            reason,
        )

    def transfer(self, source: str, target: str, count: int, reason: str | None = None) -> None:
        self._require("action")
        src, dst = self._own(source), self._own(target)
        if src is dst:
            raise RuleError("Choose two different countries")
        if count < 1 or src.soldiers - count < 1:
            raise RuleError(f"{src.name} must keep at least 1 soldier")
        src.soldiers -= count
        dst.soldiers += count
        self._log(
            "transferred",
            f"{self.current_player.name} moves {soldiers(count)} from {src.name} to {dst.name}.",
            [src, dst],
            reason,
        )

    def attack(self, source: str, target: str, reason: str | None = None) -> None:
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
            f"{self.current_player.name} attacks {dst.name} from {src.name}.",
            reason=reason,
        )

    def roll(self) -> None:
        self._require("attack")
        assert self.turn.attack is not None
        src, dst = self.country(self.turn.attack.source), self.country(self.turn.attack.target)
        dice = range(min(src.soldiers - 1, dst.soldiers))  # one attacker stays behind
        pairs = [(self.rng.randint(1, 6), self.rng.randint(1, 6)) for _ in dice]
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
            self._conquer(dst)
        elif src.soldiers == 1:
            self.turn.phase = "action"
            self._log(
                "repelled", f"{src.name} is down to 1 soldier: the attack on {dst.name} fails."
            )

    def fight(self) -> None:
        self._require("attack")
        while self.turn.phase == "attack":
            self.roll()

    def stop(self, reason: str | None = None) -> None:
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

    def _require(self, phase: Phase) -> None:
        if self.turn.phase != phase:
            raise RuleError(f"Not allowed during the {self.turn.phase} phase")

    def _own(self, code: str) -> Country:
        country = self.country(code)
        if country.owner != self.turn.player:
            raise RuleError(f"{country.name} is not yours")
        return country

    def _conquer(self, dst: Country) -> None:
        loser = self.player(dst.owner)
        bonus = conquest_bonus(dst.value)
        dst.owner = self.turn.player
        dst.soldiers = bonus
        self.turn.phase = "action"
        self._log(
            "conquered",
            f"{self.current_player.name} conquers {dst.name} and gains {bonus} soldiers.",
            [dst],
        )
        if not self.countries_of(loser.id):
            self._log("eliminated", f"{loser.name} has no countries left and is out of the game.")
        if len(self.countries_of(self.turn.player)) == len(self.state.countries):
            self.turn.phase = "over"
            self.turn.winner = self.turn.player
            self._log("over", f"{self.current_player.name} wins.")

    def _next_turn(self) -> None:
        players = self.state.players
        current = players.index(self.current_player)
        for step in range(1, len(players) + 1):
            index = (current + step) % len(players)
            if self.countries_of(players[index].id):  # the eliminated are skipped
                self._start_turn(players[index], self.turn.round + (index <= current))
                return

    def _start_turn(self, player: Player, round: int) -> None:
        reinforcements = 2 * len(self.countries_of(player.id)) if round > 1 else 0
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
        dice: list[tuple[int, int]] | None = None,
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
