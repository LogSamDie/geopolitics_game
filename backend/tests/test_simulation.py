"""Random full games: the rules hold after every move, whatever the dice and the players do."""

import random

from app import npc
from app.engine import Country, Event, Game
from tests.helpers import new_game


def random_human_move(game: Game, rng: random.Random) -> None:
    turn = game.turn
    mine = game.countries_of(turn.player)
    if turn.phase == "reinforce":
        game.reinforce(rng.choice(mine).code, rng.randint(1, turn.reinforcements))
    elif turn.phase == "attack":
        game.stop() if rng.random() < 0.1 else game.roll()
    else:
        sources = [c for c in mine if c.soldiers >= 2]
        enemies = [c for c in game.state.countries if c.owner != turn.player]
        choice = rng.random()
        if choice < 0.6 and turn.attack is None and sources:
            game.attack(rng.choice(sources).code, rng.choice(enemies).code)
        elif choice < 0.8 and sources and len(mine) > 1:
            src = rng.choice(sources)
            dst = rng.choice([c for c in mine if c is not src])
            game.transfer(src.code, dst.code, rng.randint(1, src.soldiers - 1))
        else:
            game.end_turn()


class Checker:
    """Replays events the way the browser does and checks every rule along the way."""

    def __init__(self, game: Game) -> None:
        self.game = game
        self.board: dict[str, Country] = {}
        self.seen = 0

    def check(self) -> None:
        game = self.game
        for seq, event in enumerate(game.events[self.seen :], start=self.seen + 1):
            assert event.seq == seq
            self.check_event(event)
        self.seen = len(game.events)
        assert game.state.seq == self.seen
        assert all(c.soldiers >= 1 for c in game.state.countries)
        assert {c.owner for c in game.state.countries} <= {p.id for p in game.state.players}
        assert {c.code: c for c in game.state.countries} == self.board
        turn = game.turn
        if turn.phase == "over":
            assert game.events[-1].kind == "over"
            assert all(c.owner == turn.winner for c in game.state.countries)
            return
        assert game.countries_of(turn.player), "the player to move still has a country"
        if turn.phase == "attack":
            assert turn.attack is not None
            src, dst = game.country(turn.attack.source), game.country(turn.attack.target)
            assert src.owner == turn.player and dst.owner != turn.player and src.soldiers >= 2
        else:
            assert turn.reinforcements == 0 or turn.phase == "reinforce"

    def check_event(self, event: Event) -> None:
        if event.kind == "rolled":
            assert event.turn.attack is not None and event.dice is not None
            src, dst = self.board[event.turn.attack.source], self.board[event.turn.attack.target]
            assert len(event.dice) == min(src.soldiers - 1, dst.soldiers)
            assert all(1 <= a <= 6 and 1 <= d <= 6 for a, d in event.dice)
            after = {c.code: c for c in event.countries}
            assert after[src.code].soldiers == src.soldiers - sum(a < d for a, d in event.dice)
            assert after[dst.code].soldiers == dst.soldiers - sum(a > d for a, d in event.dice)
        if event.kind == "turn":
            owned = sum(c.owner == event.turn.player for c in self.board.values())
            assert event.turn.reinforcements == (2 * owned if event.turn.round > 1 else 0)
        for country in event.countries:
            self.board[country.code] = country.model_copy()
        if event.kind == "over":
            assert [e.kind for e in self.game.events].count("over") == 1


def test_random_games_keep_every_rule() -> None:
    total = 0
    for seed in range(6):
        rng = random.Random(seed)
        values = [9, *(rng.randint(1, 9) for _ in range(9))]  # a strong human lasts longer
        game = new_game(values, seed=seed)
        checker = Checker(game)
        npc.run(game)
        checker.check()
        for _ in range(300):
            if game.turn.phase == "over":
                break
            random_human_move(game, rng)
            npc.run(game)
            checker.check()
        total += checker.seen
    assert total > 500
