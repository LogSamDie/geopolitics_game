<script lang="ts">
  import type { Pair } from './types'

  interface Props {
    pairs: Pair[]
    live?: boolean // animate the roll
  }
  let { pairs, live = false }: Props = $props()
</script>

<!-- Attacker dice are paper with ink pips, defender dice ink with paper pips. A losing die fades. -->
<span class="dice" class:live>
  {#each pairs as [a, d], i (i)}
    <span class="pair" style="--i: {i}" aria-label="{a} against {d}">
      <i class="die" data-pips={a} class:lost={a < d}></i>
      <i class="die defender" data-pips={d} class:lost={d < a}></i>
    </span>
  {/each}
</span>

<style>
  .dice {
    display: inline-flex;
    flex-wrap: wrap;
    gap: 0.25em 0.75em;
  }

  .pair {
    display: inline-flex;
    gap: 0.25em;
  }

  .die {
    --pip: radial-gradient(circle, currentColor 0.15em, transparent 0.21em);
    display: inline-block;
    width: 2em;
    height: 2em;
    border: 1px solid var(--ink);
    border-radius: 3px;
    background-color: var(--panel);
    color: var(--ink);
    background-image: var(--pip);
    background-position: 50% 50%;
    background-size: 0.6em 0.6em;
    background-repeat: no-repeat;
  }

  .defender {
    background-color: var(--ink);
    color: var(--panel);
  }

  .lost {
    opacity: 0.35;
  }

  [data-pips='2'] {
    background-image: var(--pip), var(--pip);
    background-position:
      25% 25%,
      75% 75%;
  }

  [data-pips='3'] {
    background-image: var(--pip), var(--pip), var(--pip);
    background-position:
      25% 25%,
      50% 50%,
      75% 75%;
  }

  [data-pips='4'] {
    background-image: var(--pip), var(--pip), var(--pip), var(--pip);
    background-position:
      25% 25%,
      75% 25%,
      25% 75%,
      75% 75%;
  }

  [data-pips='5'] {
    background-image: var(--pip), var(--pip), var(--pip), var(--pip), var(--pip);
    background-position:
      25% 25%,
      75% 25%,
      50% 50%,
      25% 75%,
      75% 75%;
  }

  [data-pips='6'] {
    background-image: var(--pip), var(--pip), var(--pip), var(--pip), var(--pip), var(--pip);
    background-position:
      25% 25%,
      25% 50%,
      25% 75%,
      75% 25%,
      75% 50%,
      75% 75%;
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
