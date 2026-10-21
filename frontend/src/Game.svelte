<script lang="ts">
  import { onMount } from 'svelte'
  import { api, message } from './lib/api'
  import { colorOf } from './lib/colors'
  import Dice from './lib/Dice.svelte'
  import Log from './lib/Log.svelte'
  import Map from './lib/Map.svelte'
  import { Playback } from './lib/playback.svelte'
  import type { Command, Kind, User } from './lib/types'

  interface Props {
    id: string
    user: User | null
  }
  let { id, user }: Props = $props()

  let playback = $state<Playback>()
  let owner = $state(false)
  let error = $state('')
  let pending = $state(false) // a command is on its way to the server
  let source = $state<string | null>(null)
  let target = $state<string | null>(null)
  let amount = $state(1)
  let copied = $state(false)
  let ended = $state(false) // the end of the game has been shown once

  onMount(() => {
    api.game(id).then(
      (view) => {
        playback = new Playback(view)
        owner = user?.id === view.owner
      },
      (e) => (error = message(e)),
    )
    const poll = setInterval(() => {
      if (playback && !playback.over)
        api.game(id, playback.seq).then(
          (v) => playback?.add(v.events),
          () => {},
        )
    }, 2000)
    return () => {
      clearInterval(poll)
      playback?.pause()
    }
  })

  const human = $derived(playback?.players.find((p) => !p.npc))
  const last = $derived(playback?.log.at(-1))
  const turn = $derived(last?.turn)
  const mine = $derived(owner && turn?.player === human?.id)
  const myTurn = $derived(mine && playback?.busy === false && turn?.phase !== 'over')
  const from = $derived(source === null ? undefined : playback?.countries[source])
  const to = $derived(target === null ? undefined : playback?.countries[target])
  const limit = $derived(turn?.phase === 'reinforce' ? turn.reinforcements : (from?.soldiers ?? 1) - 1)
  const validAmount = $derived(Number.isInteger(amount) && amount >= 1 && amount <= limit)

  // The battle card stays up from the attack until something unrelated happens.
  const QUIET: Kind[] = ['turn', 'reinforced', 'transferred', 'skipped']
  const inBattle = $derived(turn?.attack != null && last !== undefined && !QUIET.includes(last.kind))
  const roll = $derived(
    playback?.log.slice(playback.log.findLastIndex((e) => e.kind === 'attacked')).findLast((e) => e.kind === 'rolled'),
  )
  const fighting = $derived(turn?.phase === 'attack' && turn.attack ? [turn.attack.source, turn.attack.target] : [])
  const marked = $derived(fighting.length > 0 ? fighting : [source, target].filter((c) => c !== null))

  $effect(() => {
    if (turn?.phase === 'over') ended = true
  })

  const nameOf = (playerId: string | null) => playback?.players.find((p) => p.id === playerId)?.name ?? ''
  const count = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`
  const soldiers = (n: number) => count(n, 'soldier', 'soldiers')

  // Countries and soldiers held by each player, for the legend.
  const tally = $derived.by(() => {
    const rows: Record<string, { countries: number; soldiers: number }> = {}
    for (const c of Object.values(playback?.countries ?? {})) {
      const row = (rows[c.owner] ??= { countries: 0, soldiers: 0 })
      row.countries += 1
      row.soldiers += c.soldiers
    }
    return rows
  })

  const heading = $derived.by(() => {
    if (!turn || !human) return ''
    if (turn.phase === 'over')
      return turn.winner === null ? `${human.name} is out of the game` : `${nameOf(turn.winner)} holds the world`
    if (!myTurn) return mine ? 'Your turn' : `${nameOf(turn.player)}'s turn`
    if (turn.phase === 'reinforce') return `Place ${soldiers(turn.reinforcements)}`
    if (turn.phase === 'attack') return 'Your attack'
    return turn.attack ? 'Your attack is over' : 'Your move'
  })

  async function play(command: Command): Promise<void> {
    error = ''
    pending = true
    try {
      const view = await api.play(id, command)
      playback?.add(view.events)
      source = null
      target = null
      amount = 1
    } catch (e) {
      error = message(e)
    } finally {
      pending = false
    }
  }

  function select(code: string): void {
    if (!turn || !human || !playback) return
    const own = playback.countries[code]?.owner === human.id
    if (turn.phase === 'reinforce') {
      if (own) source = code
    } else if (turn.phase === 'action') {
      if (code === source) {
        source = null // clicking the source again clears the choice
        target = null
      } else if (source === null) {
        if (own) source = code
      } else {
        target = code
      }
    }
  }

  function copyLink(): void {
    navigator.clipboard.writeText(location.href).then(() => {
      copied = true
      setTimeout(() => (copied = false), 2000)
    })
  }
</script>

{#if playback && turn && human}
  <div class="layout">
    <header>
      <a class="brand" href="/">Geopolitics</a>
      <span class="status">
        {#if turn.phase === 'over'}
          The game is over
        {:else}
          Round {turn.round}: <i class="swatch" style:--owner={colorOf(playback.players, turn.player)}></i>
          {mine ? 'your turn' : `${nameOf(turn.player)}'s turn`}
        {/if}
      </span>
      <label>
        <input type="checkbox" bind:checked={playback.fast} onchange={() => (playback?.pause(), playback?.play())} />
        Fast-forward
      </label>
      <button class="copy" onclick={copyLink}>{copied ? 'Link copied' : 'Copy link'}</button>
    </header>

    <div class="board">
      <Map countries={playback.countries} players={playback.players} {marked} onselect={myTurn ? select : undefined} />
      {#if inBattle && turn.attack && last}
        {@const src = playback.countries[turn.attack.source]}
        {@const dst = playback.countries[turn.attack.target]}
        <div class="battle">
          <div class="fight">
            <div class="sides">
              {#each [src, dst] as side, i (i)}
                <span
                  ><i class="swatch" style:--owner={colorOf(playback.players, side?.owner ?? '')}></i>
                  {side?.name}</span
                >
                <b>{side?.soldiers}</b>
              {/each}
            </div>
            {#if roll?.dice}
              {#key roll.seq}<Dice pairs={roll.dice} live={!playback.fast} />{/key}
            {/if}
          </div>
          <p>{last.text}</p>
          {#if myTurn && turn.phase === 'attack'}
            <div class="row">
              <button class="primary" disabled={pending} onclick={() => play({ kind: 'roll' })}>Roll</button>
              <button disabled={pending} onclick={() => play({ kind: 'stop' })}>Stop attack and end turn</button>
            </div>
          {/if}
        </div>
      {/if}
    </div>

    {#if ended}
      <div class="replay">
        <button onclick={() => playback?.replay()}>Replay</button>
        <input
          type="range"
          min="1"
          max={playback.events.length}
          bind:value={playback.shown}
          aria-label="Replay position"
        />
        <span class="muted">Step {playback.shown} of {playback.events.length}</span>
      </div>
    {/if}

    <aside>
      <section class="action">
        <h3>{heading}</h3>
        {#if last?.reason}<p class="muted"><em>{last.reason}</em></p>{/if}
        {#if last && !inBattle}<p>{last.text}</p>{/if}
        <fieldset disabled={pending}>
          {#if !owner}
            <p class="muted">
              You are watching this game.
              {#if !user}<a href="/">Log in</a> to start your own.{/if}
            </p>
          {:else if myTurn && turn.phase === 'reinforce'}
            <p class="muted">
              {from
                ? `${from.name} has ${soldiers(from.soldiers)}. How many to add?`
                : 'Click one of your countries on the map.'}
            </p>
            {#if from}
              <div class="row">
                <input type="number" inputmode="numeric" min="1" max={limit} bind:value={amount} />
                <button
                  class="primary"
                  disabled={!validAmount}
                  onclick={() => play({ kind: 'reinforce', country: from.code, soldiers: amount })}
                >
                  Place
                </button>
                {#if turn.reinforcements > 1}
                  <button
                    onclick={() => play({ kind: 'reinforce', country: from.code, soldiers: turn.reinforcements })}
                  >
                    Place all {turn.reinforcements}
                  </button>
                {/if}
              </div>
            {/if}
          {:else if myTurn && turn.phase === 'action'}
            <p class="muted">
              {#if !from && turn.attack}
                You can still move soldiers: click one of your countries, then another. Then end the turn.
              {:else if !from}
                Click one of your countries, then a target: an enemy to attack, or your own to move soldiers.
              {:else if !to}
                From {from.name} ({soldiers(from.soldiers)}). Now click a target.
              {/if}
            </p>
            {#if from && to && to.owner === human.id}
              <div class="row">
                <span>{from.name} to {to.name}:</span>
                <input type="number" inputmode="numeric" min="1" max={limit} bind:value={amount} />
                <button
                  class="primary"
                  disabled={!validAmount}
                  onclick={() => play({ kind: 'transfer', source: from.code, target: to.code, soldiers: amount })}
                >
                  Move
                </button>
              </div>
              {#if from.soldiers < 2}<p class="muted">{from.name} must keep at least 1 soldier.</p>{/if}
            {:else if from && to}
              <div class="row">
                <span>{from.name} ({from.soldiers}) against {to.name} ({to.soldiers}):</span>
                <button
                  class="primary"
                  disabled={turn.attack !== null || from.soldiers < 2}
                  onclick={() => play({ kind: 'attack', source: from.code, target: to.code })}
                >
                  Attack
                </button>
              </div>
              {#if turn.attack}
                <p class="muted">You have already attacked this turn.</p>
              {:else if from.soldiers < 2}
                <p class="muted">A country needs at least 2 soldiers to attack.</p>
              {/if}
            {/if}
            <div class="row">
              <button onclick={() => play({ kind: 'end_turn' })}
                >{turn.attack ? 'End turn' : 'Skip attack and end turn'}</button
              >
            </div>
          {/if}
        </fieldset>
        {#if error}<p class="error">{error}</p>{/if}
      </section>

      <section class="legend">
        {#each playback.players as player (player.id)}
          {@const row = tally[player.id]}
          <div class:current={turn.phase !== 'over' && player.id === turn.player} class:out={!row}>
            <i class="swatch" style:--owner={colorOf(playback.players, player.id)}></i>
            <span>{player.name}{!player.npc && owner ? ' (you)' : ''}</span>
            <span class="muted"
              >{row ? `${count(row.countries, 'country', 'countries')}, ${soldiers(row.soldiers)}` : 'out'}</span
            >
          </div>
        {/each}
      </section>

      <Log events={playback.log} />
    </aside>
  </div>
{:else if error}
  <p class="error notice">{error} <a href="/">Back to the start</a></p>
{:else}
  <p class="muted notice">Loading the game…</p>
{/if}

<style>
  .layout {
    display: grid;
    grid-template-columns: 1fr 23rem;
    grid-template-rows: auto 1fr auto;
    grid-template-areas:
      'header header'
      'board aside'
      'replay aside';
    height: 100dvh;
  }

  header {
    grid-area: header;
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 0.4rem 1.25rem;
    min-height: 2.75rem;
    padding: 0.4rem 1rem;
    border-bottom: 1px solid var(--ink);
  }

  header label {
    cursor: pointer;
  }

  .brand {
    font-variant: small-caps;
    letter-spacing: 0.06em;
    font-weight: 700;
    color: var(--ink);
    text-decoration: none;
  }

  .status {
    flex: 1 0 auto;
  }

  .copy {
    min-width: 7em;
  }

  .board {
    grid-area: board;
    position: relative;
    min-height: 0;
  }

  /* The battle, pinned to the foot of the plate like a cartouche. */
  .battle {
    position: absolute;
    left: 1rem;
    right: 1rem;
    bottom: 1rem;
    z-index: 1;
    max-width: 34rem;
    margin: 0 auto;
    padding: 0.6rem 0.9rem;
    background: var(--panel);
    border: 1px solid var(--ink);
    box-shadow: 0 0 0 3px var(--panel);
  }

  .fight {
    display: flex;
    gap: 0.75rem;
  }

  .sides {
    display: grid;
    grid-template-columns: auto auto;
    grid-template-rows: 2em 2em;
    gap: 0.25em 0.5em;
    align-items: center;
    white-space: nowrap;
  }

  .sides b {
    text-align: right;
  }

  .battle p {
    margin: 0.5rem 0 0;
  }

  .replay {
    grid-area: replay;
    display: flex;
    gap: 0.75rem;
    align-items: center;
    padding: 0.4rem 1rem;
    border-top: 1px solid var(--ink);
  }

  .replay input {
    flex: 1;
    padding: 0;
    border: 0;
  }

  .replay span {
    min-width: 8em;
  }

  aside {
    grid-area: aside;
    display: grid;
    grid-template-rows: auto auto minmax(10rem, 1fr);
    min-height: 0;
    padding: 0.75rem 1rem;
    background: var(--panel);
    border-left: 1px solid var(--ink);
    overflow-y: auto;
  }

  aside > :global(* + *) {
    margin-top: 0.75rem;
    padding-top: 0.75rem;
    border-top: 1px solid var(--rule);
  }

  .action {
    min-height: 7rem; /* so the legend does not jump as the prompt changes */
  }

  fieldset {
    margin: 0;
    padding: 0;
    border: 0;
  }

  .legend {
    display: grid;
    gap: 0.1rem;
    font-size: 13px;
  }

  .legend div {
    display: grid;
    grid-template-columns: auto 1fr auto;
    gap: 0.5rem;
    align-items: center;
    padding: 0.1rem 0.4rem;
    margin: 0 -0.4rem;
  }

  .legend .current {
    background: var(--paper);
    font-weight: 700;
  }

  .legend .out {
    color: var(--muted);
  }

  .legend .out span:first-of-type {
    text-decoration: line-through;
  }

  @media (max-width: 800px) {
    .layout {
      grid-template-columns: 1fr;
      grid-template-rows: auto 55vh auto auto;
      grid-template-areas:
        'header'
        'board'
        'replay'
        'aside';
      height: auto;
    }

    .battle {
      font-size: 13px;
    }

    aside {
      border-left: 0;
      border-top: 1px solid var(--ink);
    }

    aside :global(ol) {
      max-height: 50vh;
    }
  }
</style>
