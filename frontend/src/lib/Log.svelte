<script lang="ts">
  import Dice from './Dice.svelte'
  import type { GameEvent } from './types'

  interface Props {
    events: GameEvent[]
  }
  let { events }: Props = $props()

  let list: HTMLOListElement

  $effect(() => {
    void events.length
    list.scrollTop = list.scrollHeight
  })
</script>

<ol bind:this={list}>
  {#each events as event (event.seq)}
    <li class={event.kind}>
      {event.text}
      {#if event.reason !== null}
        <em>{event.reason}</em>
      {/if}
      {#if event.dice}
        <span class="dice"><Dice pairs={event.dice} /></span>
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
