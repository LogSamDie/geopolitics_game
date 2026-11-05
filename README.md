# Geopoly

## Getting started

This is [Geopoly](geopo.ly), a browser-based geopolitics game modeled after the 1957 strategic board game [_Risk_](<https://en.wikipedia.org/wiki/Risk_(game)>). It is a single player game where one competes against NPCs.

It's implemented as a Single Page App with an API server written in Python. The frontend uses the [Svelte](https://svelte.dev/) framework and the backend uses the [FastAPI](https://fastapi.tiangolo.com/) framework. MongoDB is used as the database and the DeepSeek API is used to enhance it with AI features.

Games can be shared using a link and watched or replayed by other people. Here is an example game which may be replayed: https://geopo.ly/games/6ae90059cd926d481be7eae2

## Deployment

The application, including the frontend bundle is packaged into a [Docker Container Image](https://docs.docker.com/get-started/docker-concepts/the-basics/what-is-an-image/).

The repository is hosted on GitHub and on any push, the image is built and pushed to its public image registry. A server continuously watches this registry and pulls and deploys any newly available image. The server runs Docker and is hosted at [Hetzner](https://www.hetzner.com/).

For the database, the hosted [MongoDB Atlas](https://www.mongodb.com/products/platform/atlas-database) product is used. The backend also has a DeepSeek AI API key and the domain pointing to the production application is [geopo.ly](https://geopo.ly).

## Development (how to run)

For development, run the database, the API and the frontend separately:

```sh
# Start the/a database
docker compose up mongo # Available at localhost:27017

# Start the backend
cd backend && uv sync && uv run uvicorn app.main:app --reload # Available at localhost:8000

# Start the frontend
cd frontend && npm install && npm run dev # Available at localhost:5173
```

These environment variables can be used to configure the backend:

- `COOKIE_SECURE` (set to `"true"` in production)
- `MONGO_URL` (self explanatory, pointed at Atlas in production)
- `MONGO_DB` (e.g. `geopoly`)
- `DEEPSEEK_API_KEY` (a deepseek ai api key with some funds loaded up)

## Extra features

- Each game can be replayed and each move can be scrubbed through with a slider.
- With a shared game link, one can view a game going on in real time.
- The NPCs have made up names and personalities. The personalities do currently _not_ affect their playstyle but do affect interactions with them.
- NPCs will send funny custom letters/notes (for example if they lose against the player).
- The AI based commentary uses real locations of the countries where battles are happening.
- Exchanging soldiers and attacking are animated.
- All game moves and dice rolls are calculated on the server side, so that browser side cheating is not possible.

## Future ideas

There are currently no alliances/diplomacy. There are no analytics besides the data in the database and logs. There are no difficulty levels to choose from (besides choosing the country which influences the starting soldier count).

The NPC play style is heuristic and currently not based on AI. It is intentionally kept simple as one of the next features could be to add some AI controlled NPCs. Note that a player currently may learn how to outsmart the NPC engine by playing a few games!

Since the DeepSeek AI API is so easy to use and cheap, there could be a lot more AI influenced features in the future, such as more immersively described battles, AI created mini games in battles etc.

One thing I'd like to add next are sound effects and images/drawings of the NPC personalities.

## AI

AI is used at runtime while playing the game. Also, some AI was used during the creation of the project, the extent of which is explained below.

### At runtime

AI features are implemented and kept in `backend/app/commentary.py`. The AI model used is DeepSeek v4.1 Flash, a cheap, fast but competent model.

The model is given a system prompt as well as the game state and a few of the previously made moves. It is instructed to return commentary based on that which includes real places of the countries in a battle. It is instructed to return the output in JSON format.

### During development

It's important to say: while AI has gotten good enough to program complicated code, one must be responsible and reasonable in reviewing and curating any outputs. Also, AI is not yet good enough at prose, so e.g. this README is fully human written.

During development, I was assisted by Claude Code, though making important decisions myself (e.g. what map library to use, how auth should work) and following the principles explained above. Critical sections were implemented by hand.

