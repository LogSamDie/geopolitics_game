<script lang="ts">
  import Game from './Game.svelte'
  import Home from './Home.svelte'
  import { api } from './lib/api'
  import { route } from './lib/router.svelte'
  import type { User } from './lib/types'

  let user = $state<User | null | undefined>() // undefined until we know whether we are logged in
  const gameId = $derived(/^\/games\/([^/]+)\/?$/.exec(route.path)?.[1])

  api.me().then(
    (me) => (user = me),
    () => (user = null),
  )
</script>

{#if user === undefined}
  <p class="muted notice">Loading…</p>
{:else if gameId !== undefined}
  {#key gameId}<Game id={gameId} {user} />{/key}
{:else}
  <Home {user} onuser={(u) => (user = u)} />
{/if}
