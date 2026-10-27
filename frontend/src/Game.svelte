<script lang="ts">
  import { onMount, untrack } from 'svelte'
  import { api, message } from './lib/api'
  import { colorOf } from './lib/colors'
  import Dice from './lib/Dice.svelte'
  import Log from './lib/Log.svelte'
  import Map from './lib/Map.svelte'
  import { Playback } from './lib/playback.svelte'
  import type { Command, GameView, Route, User } from './lib/types'

  interface Props {
    view: GameView
    user: User | null
  }
  let { view, user }: Props = $props()

  const playback = new Playback(untrack(() => view))
  const owner = $derived(user?.id === view.owner)
  let error = $state('')
  let pending = $state(false)
  let source = $state<string | null>(null)
  let target = $state<string | null>(null)
  let amount = $state(1)
  let copied = $state(false)
  let ended = $state(false) // the end of the game has been shown

  onMount(() => {
    const poll = setInterval(() => {
      if (!playback.over)
        api.game(view.id, playback.seq).then(
          (v) => playback.add(v.events),
          () => {},
        )
    }, 2000)
    return () => {
      clearInterval(poll)
      playback.pause()
    }
  })

  const last = $derived(playback.log.at(-1)!)
  const turn = $derived(last.turn)
  const countries = $derived(Object.values(playback.countries))
  const mine = $derived(owner && turn.player === playback.human)
  const myTurn = $derived(mine && !playback.busy && turn.phase !== 'over')
  const canPick = $derived(myTurn && !pending && turn.phase !== 'attack')
  const from = $derived(source ? playback.countries[source] : undefined)
  const to = $derived(target ? playback.countries[target] : undefined)
  const limit = $derived(turn.phase === 'reinforce' ? turn.reinforcements : (from?.soldiers ?? 1) - 1)
  const validAmount = $derived(Number.isInteger(amount) && amount >= 1 && amount <= limit)
  const held = $derived(countries.filter((c) => c.owner === playback.human))
  const out = $derived(owner && held.length === 0 && countries.some((c) => c.owner !== turn.player))
  const canMove = $derived(held.length > 1 && held.some((c) => c.soldiers > 1))
  const sides = $derived(
    turn.attack && last.kind !== 'transferred' && last.kind !== 'over'
      ? [playback.countries[turn.attack.source], playback.countries[turn.attack.target]]
      : undefined,
  )
  const roll = $derived(playback.log.findLast((e) => e.kind === 'rolled' || e.kind === 'attacked'))
  const route = $derived.by((): Route | undefined => {
    if (turn.phase === 'attack' && turn.attack) return { ...turn.attack, attack: true, live: true }
    if (source && target) return { source, target, attack: to?.owner !== playback.human, live: false }
    if (!source && last.kind === 'transferred' && playback.running)
      return { source: last.countries[0].code, target: last.countries[1].code, attack: false, live: true }
  })
  const marked = $derived(route ? [route.source, route.target] : source ? [source] : [])

  $effect(() => {
    if (turn.phase === 'over') ended = true
  })

  // A choice made in one turn means nothing in the next, even if that turn was played elsewhere.
  $effect(() => {
    if (myTurn) return
    clearChoice()
    error = ''
  })

  function clearChoice(): void {
    source = null
    target = null
    amount = 1
  }

  const nameOf = (playerId: string | null) => view.state.players.find((p) => p.id === playerId)?.name
  const soldiers = (n: number) => `${n} ${n === 1 ? 'soldier' : 'soldiers'}`

  const heading = $derived.by(() => {
    if (turn.phase === 'over') {
      if (owner && turn.winner === playback.human) return 'You won'
      return `${owner ? 'You lost. ' : ''}${nameOf(turn.winner)} wins`
    }
    if (out) return 'You are out of the game'
    const round = `Round ${turn.round}: `
    if (mine && turn.phase === 'attack') return round + 'your attack'
    if (!myTurn) return round + (mine ? 'your turn' : `${nameOf(turn.player)}'s turn`)
    if (turn.phase === 'reinforce') return round + `place ${soldiers(turn.reinforcements)}`
    return round + (turn.attack ? 'your attack is over' : 'your move')
  })

  const speedLabel = $derived.by(() => {
    if (playback.fast) return 'Normal speed'
    if (ended || !owner || mine) return 'Fast-forward'
    if (out) return 'Fast-forward to the end'
    return playback.over ? 'Fast-forward' : 'Fast-forward to my turn'
  })

  const hint = $derived.by(() => {
    if (!myTurn) return ''
    if (turn.phase === 'reinforce')
      return from ? `${from.name} has ${soldiers(from.soldiers)}. How many to add?` : 'Pick one of your countries.'
    if (turn.phase !== 'action') return ''
    if (!from) {
      if (!turn.attack)
        return 'Pick one of your countries, then a target: an enemy to attack, or your own to move soldiers.'
      return canMove
        ? 'You can still move soldiers: pick one of your countries, then another. Then end the turn.'
        : 'Nothing left to move. End the turn.'
    }
    if (!to) return `From ${from.name} (${soldiers(from.soldiers)}). Now pick a target.`
    if (to.owner === playback.human) return from.soldiers < 2 ? `${from.name} must keep at least 1 soldier.` : ''
    if (turn.attack) return 'You have already attacked this turn.'
    return from.soldiers < 2 ? 'A country needs at least 2 soldiers to attack.' : ''
  })

  async function play(command: Command): Promise<void> {
    error = ''
    pending = true
    try {
      const { events } = await api.play(view.id, command)
      if (!playback.busy) playback.pause() // the player's own move shows at once
      playback.add(events)
      clearChoice()
    } catch (e) {
      error = message(e)
    } finally {
      pending = false
    }
  }

  function select(code: string): void {
    error = ''
    const own = playback.countries[code].owner === playback.human
    if (code === source) clearChoice()
    else if (turn.phase === 'action' && source) target = code
    else if (own) source = code
  }

  function copyLink(): void {
    navigator.clipboard.writeText(location.href).then(() => {
      copied = true
      setTimeout(() => (copied = false), 2000)
    })
  }
</script>

<div class="layout">
  <header>
    <a class="brand" href="/">Geopoly</a>
    <button class="copy" onclick={copyLink}>{copied ? 'Link copied' : 'Copy link'}</button>
  </header>

  <div class="board">
    <Map countries={playback.countries} {marked} {route} onselect={canPick ? select : undefined} />
  </div>

  <div class="panel">
    <h3 class:result={out || turn.phase === 'over'}>
      <i class="swatch" style:--owner={colorOf(out ? playback.human : turn.player)}></i>
      {heading}
    </h3>
    {#if sides}
      <div class="fight">
        <div class="sides">
          {#each sides as side (side.code)}
            <span><i class="swatch" style:--owner={colorOf(side.owner)}></i> {side.name}</span>
            <b>{side.soldiers}</b>
          {/each}
        </div>
        {#if roll?.dice}
          {#key roll.seq}<Dice {roll} live={!playback.fast} />{/key}
        {/if}
      </div>
    {/if}
    {#if last.kind !== 'turn' && last.kind !== 'over'}<p>{last.text}</p>{/if}
    {#if last.reason}<p class="muted"><em>{last.reason}</em></p>{/if}
    {#if error}<p class="error">{error}</p>{/if}
    {#if playback.playing}
      <button class="speed" onclick={() => playback.toggleSpeed()}>{speedLabel}</button>
    {/if}
    <fieldset disabled={pending}>
      {#if !owner}
        <p class="muted">
          You are watching this game.
          {#if !user}<a href="/">Log in</a> to start your own.{/if}
        </p>
      {:else if hint}
        <p class="muted">{hint}</p>
      {:else if out}
        <p class="muted">The others play on. Round {turn.round}: {nameOf(turn.player)}'s turn.</p>
      {/if}
      {#if mine && turn.phase === 'attack' && !playback.over}
        <!-- Locked during the pause after a result, so a double click is one click. -->
        <div class="row">
          <button class="primary" disabled={playback.running} onclick={() => play({ kind: 'roll' })}>Roll</button>
          <button disabled={playback.running} onclick={() => play({ kind: 'fight' })}>Roll to the end</button>
          <button disabled={playback.running} onclick={() => play({ kind: 'stop' })}>Stop and end turn</button>
        </div>
      {:else if myTurn && turn.phase === 'reinforce' && from}
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
            <button onclick={() => play({ kind: 'reinforce', country: from.code, soldiers: turn.reinforcements })}>
              Place all {turn.reinforcements}
            </button>
          {/if}
        </div>
      {:else if myTurn && turn.phase === 'action'}
        {#if from && to && to.owner === playback.human}
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
        {/if}
        <div class="row">
          <button disabled={playback.running} onclick={() => play({ kind: 'end_turn' })}>
            {turn.attack ? 'End turn' : 'Skip attack and end turn'}
          </button>
        </div>
      {/if}
    </fieldset>
  </div>

  {#if ended}
    <div class="replay">
      <button class="toggle" onclick={() => playback.toggle()}>
        {playback.playing ? 'Stop' : playback.busy ? 'Play' : 'Replay'}
      </button>
      <input
        type="range"
        min="1"
        max={playback.events.length}
        bind:value={playback.shown}
        oninput={() => playback.pause()}
        aria-label="Replay position"
      />
      <span class="muted">Step {playback.shown} of {playback.events.length}</span>
    </div>
  {/if}

  <aside>
    <section class="countries">
      {#each countries as country (country.code)}
        <button
          class:current={turn.phase !== 'over' && country.owner === turn.player}
          class:marked={marked.includes(country.code)}
          disabled={!canPick}
          onclick={() => select(country.code)}
        >
          <span><i class="swatch" style:--owner={colorOf(country.owner)}></i> {country.name}</span>
          <small class="muted">{owner && country.owner === playback.human ? 'you' : nameOf(country.owner)}</small>
          <b>{country.soldiers}</b>
        </button>
      {/each}
    </section>

    <Log events={playback.log} />
  </aside>
</div>

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

  .brand {
    margin-right: auto;
    font-variant: small-caps;
    letter-spacing: 0.06em;
    font-weight: 700;
    color: var(--ink);
    text-decoration: none;
  }

  .copy {
    min-width: 7em;
  }

  .board {
    grid-area: board;
    min-height: 0;
  }

  .panel {
    grid-area: board;
    align-self: end;
    justify-self: center;
    z-index: 1;
    width: min(34rem, 100% - 2rem);
    margin-bottom: 1rem;
    padding: 0.6rem 0.9rem;
    background: var(--panel);
    border: 1px solid var(--ink);
    box-shadow: 0 0 0 3px var(--panel);
    display: flex;
    flex-direction: column;
  }

  .fight {
    display: flex;
    gap: 0.75rem;
  }

  .sides {
    flex: none;
    display: grid;
    width: 11rem;
    grid-template-columns: minmax(0, 1fr) 3ch;
    grid-template-rows: 2em 2em;
    gap: 0.25em 0.5em;
    align-items: center;
  }

  .sides span {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .sides b {
    text-align: right;
  }

  .panel p {
    margin: 0.5rem 0 0;
  }

  .speed {
    align-self: flex-end;
    min-width: 13em;
    margin-top: 0.5rem;
  }

  .result {
    font-size: 20px;
  }

  .replay {
    grid-area: replay;
    display: flex;
    gap: 0.75rem;
    align-items: center;
    padding: 0.4rem 1rem;
    border-top: 1px solid var(--ink);
  }

  .toggle {
    min-width: 5em;
  }

  .replay input {
    flex: 1;
    min-width: 0;
    padding: 0;
    border: 0;
  }

  .replay span {
    min-width: 8em;
  }

  aside {
    grid-area: aside;
    display: grid;
    grid-template-rows: auto minmax(10rem, 1fr);
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

  fieldset {
    margin: 0;
    padding: 0;
    border: 0;
  }

  .countries {
    display: grid;
    font-size: 13px;
  }

  .countries button {
    display: grid;
    grid-template-columns: minmax(0, 1fr) auto auto;
    gap: 0.5rem;
    align-items: center;
    padding: 0.1rem 0.4rem;
    margin: 0 -0.4rem;
    border: 0;
    border-radius: 0;
    background: none;
    color: var(--ink);
    text-align: left;
  }

  .countries button:enabled:hover,
  .countries .current {
    background: var(--paper);
  }

  .countries .marked {
    outline: 1px solid var(--ink);
    outline-offset: -1px;
    font-weight: 700;
  }

  .countries span {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  @media (max-width: 800px), (max-height: 500px) {
    .layout {
      grid-template-columns: minmax(0, 1fr);
      grid-template-rows: auto max(40dvh, 16rem) auto auto auto;
      grid-template-areas:
        'header'
        'board'
        'replay'
        'panel'
        'aside';
      height: auto;
    }

    header {
      gap: 0.5rem;
      padding-inline: 0.75rem;
    }

    .panel {
      grid-area: panel;
      justify-self: stretch;
      width: auto;
      min-height: 10rem;
      margin: 0;
      border-width: 1px 0 0;
      box-shadow: none;
    }

    .panel h3 {
      order: -3;
    }

    fieldset {
      order: -2;
    }

    .speed {
      order: -1;
    }

    .fight {
      flex-wrap: wrap;
    }

    .sides {
      width: 100%;
    }

    aside {
      border-left: 0;
      border-top: 1px solid var(--ink);
    }

    .countries {
      grid-template-columns: repeat(2, minmax(0, 1fr));
      column-gap: 1.25rem;
    }

    .countries button {
      grid-template-columns: minmax(0, 1fr) auto;
      min-height: 2.25rem;
    }

    .countries small {
      display: none;
    }

    aside :global(ol) {
      max-height: 50vh;
    }
  }
</style>
