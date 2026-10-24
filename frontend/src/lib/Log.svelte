<script lang="ts">
  import Dice from './Dice.svelte'
  import type { GameEvent, Player } from './types'

  interface Props {
    events: GameEvent[]
    players: Player[]
  }
  let { events, players }: Props = $props()

  let list: HTMLOListElement
  let following = true // keep showing the newest entry unless the reader scrolled up

  $effect(() => {
    void events.length
    if (list.scrollHeight - list.clientHeight <= 40) following = true // nothing left to scroll
    if (following) list.scrollTop = list.scrollHeight
  })
</script>

<ol bind:this={list} onscroll={() => (following = list.scrollTop + list.clientHeight >= list.scrollHeight - 40)}>
  {#each events as event (event.seq)}
    <li class={event.kind}>
      {event.text}
      {#if event.reason !== null}
        <em>{event.reason}</em>
      {/if}
      {#if event.dice}
        <div class="dice"><Dice roll={event} {players} /></div>
      {/if}
    </li>
  {/each}
</ol>

<style>
  ol {
    list-style: none;
    margin: 0;
    padding: 0 0.25rem 0 0;
    overflow-y: auto;
    scrollbar-width: thin;
    display: grid;
    grid-template-columns: minmax(0, 1fr);
    gap: 0.35rem;
    align-content: start;
    font-size: 13px;
    line-height: 1.45;
  }

  li {
    padding-left: 0.75rem;
    text-indent: -0.75rem;
    animation: appear 0.25s;
  }

  li.turn {
    margin-top: 0.5rem;
    padding-top: 0.4rem;
    border-top: 1px solid var(--rule);
    font-weight: 700;
  }

  li.conquered,
  li.eliminated {
    font-weight: 700;
  }

  li.over {
    margin-top: 0.5rem;
    padding-top: 0.5rem;
    border-top: 3px double var(--ink);
    font-weight: 700;
  }

  em,
  .dice {
    display: block;
    text-indent: 0;
  }

  em {
    color: var(--muted);
  }

  .dice {
    font-size: 0.9em;
    margin-top: 0.2rem;
  }
</style>
