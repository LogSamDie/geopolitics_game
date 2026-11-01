<script lang="ts">
  import { api, message } from './lib/api'
  import Map from './lib/Map.svelte'
  import { navigate } from './lib/router.svelte'
  import type { Country, GameSummary, User } from './lib/types'

  let { user, onuser }: { user: User | null; onuser: (user: User | null) => void } = $props()

  let username = $state('')
  let password = $state('')
  let error = $state('')
  let countries = $state<Country[]>([])
  let games = $state<GameSummary[]>([])
  let search = $state('')
  let chosen = $state<string | null>(null)

  const plain = (text: string) => text.normalize('NFD').replace(/\p{M}/gu, '').toLowerCase()
  const matches = $derived.by(() => {
    const query = plain(search)
    const found = countries.filter((c) => plain(c.name).includes(query))
    return found.toSorted((a, b) => +plain(b.name).startsWith(query) - +plain(a.name).startsWith(query))
  })
  const selected = $derived(countries.find((c) => c.code === chosen))
  const onMap = $derived(selected ? { [selected.code]: { ...selected, owner: 'p0', soldiers: selected.value } } : {})

  $effect(() => {
    if (user === null) return
    api.countries().then(
      (c) => (countries = c),
      (e) => (error = message(e)),
    )
    api.games().then(
      (g) => (games = g),
      (e) => (error = message(e)),
    )
  })

  let busy = false

  async function attempt(action: () => Promise<unknown>): Promise<void> {
    if (busy) return
    busy = true
    error = ''
    try {
      await action()
    } catch (e) {
      error = message(e)
    } finally {
      busy = false
    }
  }

  const login = () => attempt(async () => onuser(await api.login(username, password)))
  const register = () => attempt(async () => onuser(await api.register(username, password)))
  const logout = () =>
    attempt(async () => {
      await api.logout()
      password = ''
      chosen = null
      search = ''
      games = []
      onuser(null)
    })
  const start = () => attempt(async () => navigate(`/games/${(await api.createGame(chosen!)).id}`))

  function describe(game: GameSummary): string {
    if (game.turn.phase === 'over') return game.turn.winner === game.human ? 'Won' : 'Lost'
    return `Round ${game.turn.round}, ${game.countries} of 10 countries`
  }
</script>

<div class="home">
  <header>
    <a class="brand caps" href="/">Geopoly</a>
    {#if user}
      <span class="account">
        <span class="muted name">{user.username}</span>
        <button class="quiet" onclick={logout}>Log out</button>
      </span>
    {/if}
  </header>

  <div class="board">
    <Map countries={onMap} marked={chosen ? [chosen] : []} focus={chosen} />
  </div>

  <aside>
    {#if user === null}
      <form
        onsubmit={(e) => {
          e.preventDefault()
          login()
        }}
      >
        <h2>Log in or sign up</h2>
        <p class="muted">Lead one country against nine commanders, until one of you holds all ten.</p>
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
        <label>Password <input type="password" bind:value={password} required minlength="6" maxlength="128" /></label>
        <div class="row">
          <button class="primary" type="submit">Log in</button>
          <button type="button" onclick={(e) => e.currentTarget.form?.reportValidity() && register()}>Sign up</button>
        </div>
        {#if error}<p class="error">{error}</p>{/if}
      </form>
    {:else}
      <section class="new">
        <h2>New game</h2>
        <p class="muted">Pick your country. A bigger population means more soldiers to start with.</p>
        <input
          type="search"
          placeholder="Search countries"
          aria-label="Search countries"
          bind:value={search}
          onkeydown={(e) => {
            if (e.key === 'Enter' && matches[0]) chosen = matches[0].code
          }}
        />
        <ul>
          {#each matches as country (country.code)}
            <li>
              <label class:chosen={country.code === chosen}>
                <input type="radio" name="country" value={country.code} bind:group={chosen} />
                {country.name}
                <small class="muted">{country.value} {country.value === 1 ? 'soldier' : 'soldiers'}</small>
              </label>
            </li>
          {:else}
            {#if search}<li class="muted">No country matches.</li>{/if}
          {/each}
        </ul>
        <button class="primary" disabled={!selected} onclick={start}>
          {selected ? `Start as ${selected.name}` : 'Pick a country to start'}
        </button>
        {#if error}<p class="error">{error}</p>{/if}
      </section>

      {#if games.length}
        <section class="games">
          <h2>Your games</h2>
          <ul>
            {#each games as game (game.id)}
              <li>
                <a href="/games/{game.id}">
                  {game.country}
                  <small class="muted">{describe(game)}, {new Date(game.created).toLocaleDateString()}</small>
                </a>
              </li>
            {/each}
          </ul>
        </section>
      {/if}
    {/if}
  </aside>
</div>

<style>
  .home {
    display: grid;
    grid-template-columns: minmax(0, 1fr) 23rem;
    grid-template-rows: auto minmax(0, 1fr);
    height: 100dvh;
  }

  header {
    grid-column: 1 / -1;
  }

  .account {
    display: flex;
    gap: 0.75rem;
    align-items: center;
    min-width: 0;
  }

  .name {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .account button {
    flex: none;
  }

  .board {
    min-height: 0;
  }

  aside {
    display: flex;
    flex-direction: column;
    gap: 1.25rem;
    padding: 1rem;
    background: var(--panel);
    border-left: 1px solid var(--ink);
    overflow-y: auto;
  }

  section {
    display: flex;
    flex-direction: column;
    min-height: 0;
  }

  .new {
    flex: 2;
    min-height: 22rem;
  }

  .games {
    flex: 1;
    padding-top: 1rem;
    border-top: 1px solid var(--rule);
  }

  p {
    margin: 0 0 0.75rem;
  }

  label {
    display: grid;
    gap: 0.25rem;
    margin-bottom: 0.75rem;
  }

  input {
    width: 100%;
  }

  ul {
    flex: 1;
    list-style: none;
    margin: 0.5rem 0;
    padding: 0;
    min-height: 7rem;
    overflow-y: auto;
    scrollbar-width: thin;
  }

  li label,
  li a {
    position: relative;
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    gap: 1rem;
    width: 100%;
    padding: 0.2rem 0.4rem;
    margin: 0;
    color: var(--ink);
    text-decoration: none;
    cursor: pointer;
  }

  li label:hover,
  li a:hover {
    background: var(--paper);
  }

  li input {
    position: absolute;
    width: 1px;
    opacity: 0;
  }

  .chosen {
    outline: 1px solid var(--ink);
    outline-offset: -1px;
    font-weight: 700;
  }

  li label:has(:focus-visible),
  li a:focus-visible {
    outline: 2px solid var(--accent);
    outline-offset: -2px;
  }

  @media (pointer: coarse) {
    li label,
    li a {
      padding-block: 0.55rem;
    }
  }

  @media (max-width: 800px), (max-height: 500px) {
    .home {
      grid-template-columns: minmax(0, 1fr);
      grid-template-rows: auto max(30dvh, 12rem) 1fr;
      height: auto;
      min-height: 100dvh;
    }

    aside {
      overflow: visible;
      border-left: 0;
      border-top: 1px solid var(--ink);
    }

    .new > .primary {
      position: sticky;
      bottom: 0.5rem;
    }

    ul {
      max-height: 15rem;
    }
  }
</style>
