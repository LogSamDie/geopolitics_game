# Geopoly

A single-player conquest game in the browser, built for the INF4001N entrance exam. You pick a
country, nine others go to NPCs, and whoever holds all ten wins. Anyone with a game's link can
watch it; only its logged-in owner can play.

## How to run

With Docker (the way it is deployed):

```sh
docker compose up --build
```

Open <http://localhost:8000>, sign up and start a game. MongoDB runs in its own container and
keeps its data in a named volume.

For development, run the database, the API and the frontend separately:

```sh
docker compose up mongo                                   # MongoDB on localhost:27017
cd backend && uv sync && uv run uvicorn app.main:app --reload   # API on :8000
cd frontend && npm install && npm run dev                 # Vite on :5173, proxies /api to :8000
```

Checks:

```sh
cd backend && uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pytest
cd frontend && npm run check && npm run build
```

The API tests need MongoDB. Formatters: `uv run ruff format .` and `npm run format`.

Settings are the environment variables `MONGO_URL` (default `mongodb://localhost:27017`) and
`STATIC_DIR` (`static`, where the built frontend is served from).

In VS Code, open the repository root and accept the recommended extensions.

## Stack

- **Backend**: Python 3.13, FastAPI, PyMongo's async client, fully typed (mypy strict).
- **Frontend**: Svelte 5 with TypeScript, built by Vite, MapLibre GL JS for the board.
- **Database**: MongoDB, three collections: `users`, `sessions`, `games`.
- **Deployment**: one multi-stage Docker image that builds the frontend, then serves it from
  the API process.

## How it works

The server owns every rule and dice roll. The browser sends intents (reinforce, transfer, attack,
roll, roll to the end, stop, end turn) and gets back the resulting events, including the NPC turns.
Each event carries the countries it changed and the turn as it then stood. The browser builds the
board from the events it has shown and reveals new ones with a pause, so battles and NPC decisions
play out visibly. Fast-forward shortens the pause, and the replay slider moves back through them.

- `backend/app/engine.py`: the rules.
- `backend/app/npc.py`: the NPC strategy. It reinforces its largest army, attacks the target with
  the best expected gain among those with at least even odds, withdraws below a quarter, and moves
  half the attacking army into a conquest.
- `backend/app/games.py`, `auth.py`: the HTTP API.
- `frontend/src/lib/playback.svelte.ts`: the events the UI renders from.
- `frontend/src/lib/Map.svelte`: the board.
- `scripts/build_countries.py`: builds the country data from worldometers.info and Natural Earth.

## Rules and assumptions

The rules follow the assignment. Where it leaves a gap we chose:

- The soldiers gained for a conquest (max of 2 and half the country's value) are placed in the
  conquered country. The attacker may then move more soldiers into it, or anywhere else, before
  ending the turn.
- Stopping an attack ends the turn immediately, as the assignment says. An attack that ends by
  itself (conquest, or the attacker is down to 1 soldier) leaves the player in their turn, where
  they can still move soldiers before ending it.
- Reinforcements are placed first; transfers and the attack follow. Since placing only adds
  soldiers, this never limits what a player can do with a turn.
- A player eliminated from the game is skipped. If the human player is eliminated the NPCs play on
  until one of them holds all ten countries.
- Dice are paired in the order rolled (die 1 against die 1), the higher roll wins, a tie kills
  nobody, and the number of dice is the smaller of the defender's soldiers and the attacker's
  soldiers minus one. Any country may attack any other.

## Not yet done

- LLM commentary on battles (planned with DeepSeek).
