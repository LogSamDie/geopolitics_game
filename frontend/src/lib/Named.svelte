<script lang="ts">
  import { colorOf, textOn } from './colors'
  import type { Player } from './types'

  let { text, players }: { text: string; players: Player[] } = $props()

  // Lines may capitalise a username.
  const owners = $derived(
    new Map(
      players.flatMap((p) => {
        const capitalised = p.name[0].toUpperCase() + p.name.slice(1)
        return [p.name, capitalised].map((name) => [name, p.id] as const)
      }),
    ),
  )
  const parts = $derived.by(() => {
    const names = [...owners.keys()].sort((a, b) => b.length - a.length)
    const pattern = names.map((name) => name.replace(/[.\-]/g, '\\$&')).join('|')
    return text.split(new RegExp(`\\b(${pattern})\\b`))
  })
</script>

{#each parts as part}
  {@const owner = owners.get(part)}
  {#if owner}
    {@const color = colorOf(owner)}
    <b style:background={color} style:color={textOn(color)}>{part}</b>
  {:else}
    {part}
  {/if}
{/each}

<style>
  b {
    padding: 0 0.2em;
    border-radius: 2px;
    font-weight: inherit;
  }
</style>
