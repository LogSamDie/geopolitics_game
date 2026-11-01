<script lang="ts">
  import Dice from './Dice.svelte'
  import Feed from './Feed.svelte'
  import type { GameEvent } from './types'

  let { events }: { events: GameEvent[] } = $props()
</script>

<Feed title="Game log" size={events.length}>
  {#each events as event (event.seq)}
    <li class={event.kind}>
      {event.text}
      {#if event.reason}<em class="muted">{event.reason}</em>{/if}
      {#if event.dice}<Dice roll={event} />{/if}
    </li>
  {/each}
</Feed>

<style>
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
  }

  @keyframes appear {
    from {
      opacity: 0;
    }
  }
</style>
