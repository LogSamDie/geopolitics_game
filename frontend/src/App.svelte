<script lang="ts">
  import Game from './Game.svelte'
  import Home from './Home.svelte'
  import { api, message } from './lib/api'
  import { route } from './lib/router.svelte'
  import type { User } from './lib/types'

  let user = $state<User | null | undefined>() // undefined until we know
  const gameId = $derived(/^\/games\/([^/]+)\/?$/.exec(route.path)?.[1])

  api.me().then(
    (me) => (user = me),
    () => (user = null),
  )
</script>

{#if user === undefined}
  <p class="muted notice">Loading…</p>
{:else if gameId !== undefined}
  {#key gameId}
    {#await api.game(gameId)}
      <p class="muted notice">Loading the game…</p>
    {:then view}
      <Game {view} {user} />
    {:catch e}
      <p class="error notice">{message(e)} <a href="/">Back to the start</a></p>
    {/await}
  {/key}
{:else}
  <Home {user} onuser={(u) => (user = u)} />
{/if}
