<script lang="ts">
  import { untrack } from 'svelte'
  import type { Pair } from './types'

  interface Props {
    pairs: Pair[]
    live?: boolean // animate the roll
  }
  let { pairs, live = false }: Props = $props()
  const animate = untrack(() => live) // a change of speed must not re-roll the dice on screen

  // Pips as cells of a 3x3 grid numbered 0-8 row by row; the index is the face value.
  const PIPS = [[], [4], [0, 8], [0, 4, 8], [0, 2, 6, 8], [0, 2, 4, 6, 8], [0, 2, 3, 5, 6, 8]]
</script>

{#snippet die(value: number, lost: boolean, defender: boolean)}
  <svg class="die" class:lost class:defender viewBox="0 0 20 20">
    <rect x="0.5" y="0.5" width="19" height="19" rx="2" />
    {#each PIPS[value] ?? [] as cell}<circle cx={5 + 5 * (cell % 3)} cy={5 + 5 * Math.floor(cell / 3)} r="1.8" />{/each}
  </svg>
{/snippet}

<!-- One column per pair, the attacker's die above the defender's. A losing die fades. -->
<div class="dice" class:live={animate}>
  {#each pairs as [a, d], i (i)}
    <span class="pair" style:--i={i}>{@render die(a, a < d, false)}{@render die(d, d < a, true)}</span>
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
    fill: var(--panel);
    stroke: var(--ink);
  }

  circle {
    fill: var(--ink);
  }

  .defender rect {
    fill: var(--ink);
  }

  .defender circle {
    fill: var(--panel);
  }

  .lost {
    opacity: 0.35;
  }

  /* The roll: each pair drops onto the page in turn, then a losing die settles to faded. */
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

    to {
      transform: none;
    }
  }
</style>
