<script lang="ts">
  import { untrack } from 'svelte'
  import { colorOf, textOn } from './colors'
  import type { GameEvent } from './types'

  let { roll, live = false }: { roll: GameEvent; live?: boolean } = $props()
  const animate = untrack(() => live) // a change of speed must not re-roll the dice on screen

  // Cells of a 3x3 grid, numbered row by row, for each face.
  const pips = [[], [4], [0, 8], [0, 4, 8], [0, 2, 6, 8], [0, 2, 4, 6, 8], [0, 2, 3, 5, 6, 8]]
  const colors = $derived(roll.countries.map((c) => colorOf(c.owner)))
</script>

{#snippet die(value: number, lost: boolean, color: string)}
  <svg class="die" class:lost style:fill={textOn(color)} viewBox="0 0 20 20">
    <rect x="0.5" y="0.5" width="19" height="19" rx="2" style:fill={color} />
    {#each pips[value] as cell}<circle cx={5 + 5 * (cell % 3)} cy={5 + 5 * Math.floor(cell / 3)} r="1.8" />{/each}
  </svg>
{/snippet}

<!-- A column per pair: the attacker's die above the defender's. -->
<div class="dice" class:live={animate}>
  {#each roll.dice ?? [] as [a, d], i}
    <span class="pair" style:--i={i}>{@render die(a, a < d, colors[0])}{@render die(d, d < a, colors[1])}</span>
  {/each}
</div>

<style>
  .dice {
    display: flex;
    flex-wrap: wrap;
    gap: 0.25em 0.5em;
  }

  .pair {
    display: grid;
    gap: 0.25em;
  }

  .die {
    width: 2em;
    height: 2em;
  }

  rect {
    stroke: var(--ink);
  }

  .lost {
    opacity: 0.35;
  }

  .live .die {
    animation: roll 0.5s cubic-bezier(0.2, 0.7, 0.3, 1) both;
    animation-delay: calc(var(--i) * 80ms);
  }

  @keyframes roll {
    from {
      opacity: 0;
      transform: translateY(-0.8em) rotate(-150deg);
    }

    60% {
      opacity: 1;
      transform: translateY(0.1em) rotate(12deg);
    }
  }
</style>
