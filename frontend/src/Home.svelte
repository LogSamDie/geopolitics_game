<script lang="ts">
  import { api, message } from './lib/api'
  import { navigate } from './lib/router.svelte'
  import type { CountryInfo, GameSummary, User } from './lib/types'

  interface Props {
    user: User | null
    onuser: (user: User | null) => void
  }
  let { user, onuser }: Props = $props()

  let username = $state('')
  let password = $state('')
  let error = $state('')
  let countries = $state<CountryInfo[]>([])
  let games = $state<GameSummary[]>([])
  let chosen = $state('ZA')

  $effect(() => {
    if (user === null) return
    api.countries().then((c) => (countries = c))
    api.games().then((g) => (games = g))
  })

  async function attempt(action: () => Promise<unknown>): Promise<void> {
    error = ''
    try {
      await action()
    } catch (e) {
      error = message(e)
    }
  }

  const login = () => attempt(async () => onuser(await api.login(username, password)))
  const register = () => attempt(async () => onuser(await api.register(username, password)))
  const logout = () => attempt(async () => (await api.logout(), onuser(null)))
  const start = () => attempt(async () => navigate(`/games/${(await api.createGame(chosen)).id}`))

  function describe(game: GameSummary): string {
    if (game.turn.phase === 'over') return game.turn.winner === game.human ? 'won' : 'lost'
    return `round ${game.turn.round}, ${game.countries} of 10 countries`
  }
</script>

<main>
  <div>
    <h1>Geopolitics</h1>
    <p>
      Conquer the world one country at a time. You may attack once a turn, and from the second round every country you
      hold brings two new soldiers.
    </p>
  </div>

  {#if user === null}
    <form onsubmit={(e) => (e.preventDefault(), login())}>
      <h2>Log in or sign up</h2>
      <label>
        Username
        <input
          bind:value={username}
          required
          minlength="2"
          maxlength="32"
          pattern="[A-Za-z0-9_.\-]+"
          title="Letters, digits, _ . -"
        />
      </label>
      <label>Password <input type="password" bind:value={password} required minlength="6" /></label>
      <div class="row">
        <button class="primary" type="submit">Log in</button>
        <button type="button" onclick={register}>Sign up</button>
      </div>
      {#if error}<p class="error">{error}</p>{/if}
    </form>
  {:else}
    <section>
      <h2>New game</h2>
      <label>
        Your country
        <select bind:value={chosen}>
          {#each countries as country (country.code)}
            <option value={country.code}>{country.name} ({country.value} soldiers)</option>
          {/each}
        </select>
      </label>
      <div class="row">
        <button class="primary" onclick={start}>Start</button>
        <span class="muted">Nine opponents are drawn at random from the rest of the world.</span>
      </div>
      {#if error}<p class="error">{error}</p>{/if}
    </section>

    <section>
      <h2>Your games</h2>
      {#if games.length === 0}
        <p class="muted">None yet. Pick a country above to start one.</p>
      {/if}
      <ul>
        {#each games as game (game.id)}
          <li>
            <a href="/games/{game.id}">{game.country}</a>
            <span>{describe(game)}, {new Date(game.created).toLocaleDateString()}</span>
          </li>
        {/each}
      </ul>
    </section>

    <p class="muted">Logged in as {user.username}. <button onclick={logout}>Log out</button></p>
  {/if}
</main>

<style>
  main {
    max-width: 36rem;
    margin: 0 auto;
    padding: 3rem 1rem;
    display: grid;
    gap: 2rem;
  }

  label {
    display: grid;
    gap: 0.25rem;
    margin-bottom: 0.75rem;
  }

  input,
  select {
    width: 100%;
  }

  ul {
    list-style: none;
    margin: 0;
    padding: 0;
    display: grid;
    gap: 0.35rem;
  }

  /* A table of contents: title, dotted leader, then the state of play. */
  li {
    display: flex;
    align-items: baseline;
    gap: 0.5rem;
  }

  li::after {
    content: '';
    order: 1;
    flex: 1;
    border-bottom: 1px dotted var(--rule);
    transform: translateY(-0.3em);
  }

  li span {
    order: 2;
    color: var(--muted);
  }
</style>
