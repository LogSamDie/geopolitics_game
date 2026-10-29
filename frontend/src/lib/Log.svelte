<script lang="ts">
  import Dice from './Dice.svelte'
  import type { GameEvent } from './types'

  interface Props {
    events: GameEvent[]
  }
  let { events }: Props = $props()

  let list: HTMLOListElement
  let following = true // false while the reader has scrolled up

  $effect(() => {
    void events.length
    if (list.scrollHeight - list.clientHeight <= 40) following = true
    if (following) list.scrollTop = list.scrollHeight
  })
</script>

<ol bind:this={list} onscroll={() => (following = list.scrollTop + list.clientHeight >= list.scrollHeight - 40)}>
  {#each events as event (event.seq)}
    <li class={event.kind}>
      {event.text}
      {#if event.reason}<em>{event.reason}</em>{/if}
      {#if event.dice}<Dice roll={event} />{/if}
    </li>
  {/each}
</ol>

<style>
  ol {
    list-style: none;
    margin: 0;
    padding: 0;
    overflow-y: auto;
    scrollbar-width: thin;
    display: grid;
    grid-template-columns: minmax(0, 1fr);
    gap: 0.35rem;
    align-content: start;
    font-size: 13px;
  }

  li {
    animation: appear 0.25s;
  }

  .turn,
  .conquered,
  .eliminated,
  .over {
    font-weight: 700;
  }

  .turn,
  .over {
    margin-top: 0.5rem;
    padding-top: 0.5rem;
    border-top: 1px solid var(--rule);
  }

  em {
    display: block;
    color: var(--muted);
  }

  @keyframes appear {
    from {
      opacity: 0;
    }
  }
</style>
