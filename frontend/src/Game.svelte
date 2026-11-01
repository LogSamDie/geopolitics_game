<script lang="ts">
  import { onMount, untrack } from 'svelte'
  import { api, message } from './lib/api'
  import { colorOf } from './lib/colors'
  import Dice from './lib/Dice.svelte'
  import Feed from './lib/Feed.svelte'
  import Log from './lib/Log.svelte'
  import Map from './lib/Map.svelte'
  import Named from './lib/Named.svelte'
  import { Playback } from './lib/playback.svelte'
  import type { Command, GameView, Note, Route, User } from './lib/types'

  let { view, user }: { view: GameView; user: User | null } = $props()

  const playback = new Playback(untrack(() => view))
  const isOwner = $derived(user?.id === view.owner)
  let error = $state('')
  let pending = $state(false)
  let source = $state<string | null>(null)
  let target = $state<string | null>(null)
  let amount = $state(1)
  let copied = $state(false)
  let ended = $state(false) // the end of the game has been shown
  let asking = $state(false)
  let dismissed = $state(0) // the last commander's message read

  onMount(() => {
    const poll = setInterval(() => {
      if (playback.over && !playback.pending) return
      const seq = playback.seq
      api.game(view.id, seq).then(
        (v) => {
          if (seq === playback.seq) playback.update(v) // else a move has overtaken this poll
        },
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
  const humanToMove = $derived(isOwner && turn.player === playback.human)
  const canAct = $derived(humanToMove && !playback.busy && turn.phase !== 'over')
  const canPick = $derived(canAct && !pending && !asking && turn.phase !== 'attack')
  const from = $derived(source ? playback.countries[source] : undefined)
  const to = $derived(target ? playback.countries[target] : undefined)
  const limit = $derived(turn.phase === 'reinforce' ? turn.reinforcements : (from?.soldiers ?? 1) - 1)
  const validAmount = $derived(Number.isInteger(amount) && amount >= 1 && amount <= limit)
  const held = $derived(countries.filter((c) => c.owner === playback.human))
  const out = $derived(isOwner && held.length === 0 && countries.some((c) => c.owner !== turn.player))
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
  const told = $derived(playback.notes.filter((n) => n.seq <= last.seq))
  // The notes in order, with null where battles went by without any, as after the player is out.
  // Battles are written in order, so only those after the last line can still get one.
  const feed = $derived.by(() => {
    if (!told.length) return []
    const written = playback.pending ? (told.findLast((n) => n.kind !== 'advice')?.seq ?? 0) : Infinity
    const items: (Note | null)[] = []
    for (const event of playback.log) {
      const notes = told.filter((n) => n.seq === event.seq)
      if (event.kind === 'attacked' && event.seq <= written && !notes.length && items.at(-1) !== null) items.push(null)
      items.push(...notes)
    }
    return items
  })
  const line = $derived(told.find((n) => n.kind === 'line' && n.seq === last.seq))
  const advice = $derived(humanToMove ? told.find((n) => n.kind === 'advice' && n.round === turn.round) : undefined)
  // A commander's message waits for a calm moment in the player's move, or goes out once they
  // have no moves left. It is gone after their next move, and from replays.
  const letter = $derived.by(() => {
    if (!isOwner || ended || (held.length && (!canAct || source || pending))) return
    const move = playback.log.findLast((e) => e.turn.player === playback.human && e.kind !== 'turn')
    return told.findLast((n) => n.kind === 'letter' && n.seq >= (move?.seq ?? 0) && n.seq > dismissed)
  })
  const marked = $derived(route ? [route.source, route.target] : source ? [source] : [])

  $effect(() => {
    if (turn.phase === 'over') ended = true
  })

  // A choice made in one turn means nothing in the next, even if that turn was played elsewhere.
  $effect(() => {
    if (canAct) return
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
      if (isOwner && turn.winner === playback.human) return 'You won'
      return `${isOwner ? 'You lost. ' : ''}${nameOf(turn.winner)} wins`
    }
    if (out) return 'You are out of the game'
    const round = `Round ${turn.round}: `
    if (humanToMove && turn.phase === 'attack') return round + 'your attack'
    if (!canAct) return round + (humanToMove ? 'your turn' : `${nameOf(turn.player)}'s turn`)
    if (turn.phase === 'reinforce') return round + `place ${soldiers(turn.reinforcements)}`
    return round + (turn.attack ? 'your attack is over' : 'your move')
  })

  const speedLabel = $derived.by(() => {
    if (playback.fast) return 'Normal speed'
    if (ended || !isOwner || humanToMove) return 'Fast-forward'
    if (out) return 'Fast-forward to the end'
    return playback.over ? 'Fast-forward' : 'Fast-forward to my turn'
  })

  const hint = $derived.by(() => {
    if (!canAct) return ''
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
      const moved = await api.play(view.id, command)
      if (!playback.busy) playback.pause() // the player's own move shows at once
      playback.update(moved)
      clearChoice()
    } catch (e) {
      error = message(e)
    } finally {
      pending = false
    }
  }

  async function ask(): Promise<void> {
    error = ''
    asking = true
    try {
      playback.update(await api.advice(view.id))
    } catch (e) {
      error = message(e)
    } finally {
      asking = false
    }
  }

  function select(code: string): void {
    error = ''
    if (code === source) clearChoice()
    else if (turn.phase === 'action' && source) target = code
    else if (playback.countries[code].owner === playback.human) source = code
  }

  const open = (dialog: HTMLDialogElement) => dialog.showModal()

  function copyLink(): void {
    navigator.clipboard.writeText(location.href).then(() => {
      copied = true
      setTimeout(() => (copied = false), 2000)
    })
  }
</script>

{#snippet advised(note: Note)}
  <Named text="{nameOf(playback.human)} was advised by their commanders:" players={view.state.players} />
  <blockquote><Named text="“{note.text}”" players={view.state.players} /></blockquote>
{/snippet}

<div class="layout">
  <header>
    <a class="brand caps" href="/">Geopoly</a>
    <button class="copy" onclick={copyLink}>{copied ? 'Link copied' : 'Copy link'}</button>
  </header>

  <div class="board">
    <Map countries={playback.countries} {marked} {route} onselect={canPick ? select : undefined} />
  </div>

  <div class="panel">
    <div class="title">
      <h2 class:result={out || turn.phase === 'over'}>
        <i class="swatch" style:background={colorOf(out ? playback.human : turn.player)}></i>
        {heading}
      </h2>
      {#if canAct && turn.phase !== 'attack' && !advice}
        <button class="quiet" disabled={asking || pending} onclick={ask}>
          {asking ? 'Asking your commanders…' : 'Ask your commanders'}
        </button>
      {/if}
    </div>
    {#if sides}
      <div class="fight">
        <div class="sides">
          {#each sides as side (side.code)}
            <span><i class="swatch" style:background={colorOf(side.owner)}></i> {side.name}</span>
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
    {#if line}<p class="line"><Named text={line.text} players={view.state.players} /></p>{/if}
    {#if advice}<div class="advice">{@render advised(advice)}</div>{/if}
    {#if error}<p class="error">{error}</p>{/if}
    {#if playback.playing}
      <button class="speed" onclick={() => playback.toggleSpeed()}>{speedLabel}</button>
    {/if}
    <fieldset disabled={pending || asking}>
      {#if !isOwner}
        <p class="muted">
          You are watching this game.
          {#if !user}<a href="/">Log in</a> to start your own.{/if}
        </p>
      {:else if hint}
        <p class="muted">{hint}</p>
      {:else if out}
        <p class="muted">The others play on. Round {turn.round}: {nameOf(turn.player)}'s turn.</p>
      {/if}
      {#if humanToMove && turn.phase === 'attack' && !playback.over}
        <!-- Locked during the pause after a result, so a double click is one click. -->
        <div class="row">
          <button class="primary" disabled={playback.running} onclick={() => play({ kind: 'roll' })}>Roll</button>
          <button disabled={playback.running} onclick={() => play({ kind: 'fight' })}>Roll to the end</button>
          <button disabled={playback.running} onclick={() => play({ kind: 'stop' })}>Stop and end turn</button>
        </div>
      {:else if canAct && turn.phase === 'reinforce' && from}
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
      {:else if canAct && turn.phase === 'action'}
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
      <button aria-label="Previous step" disabled={playback.shown <= 1} onclick={() => playback.move(-1)}>‹</button>
      <button class="toggle" onclick={() => playback.toggle()}>
        {playback.playing ? 'Stop' : playback.busy ? 'Play' : 'Replay'}
      </button>
      <button aria-label="Next step" disabled={!playback.busy} onclick={() => playback.move(1)}>›</button>
      <input
        type="range"
        min="1"
        max={playback.events.length}
        bind:value={playback.shown}
        oninput={() => playback.pause()}
        aria-label="Replay position"
      />
      <span class="muted">{playback.shown} / {playback.events.length}</span>
    </div>
  {/if}

  {#if letter}
    <dialog use:open onclose={() => (dismissed = letter.seq)}>
      <h2><i class="swatch" style:background={colorOf(letter.player!)}></i> {nameOf(letter.player)} writes</h2>
      <p>“<Named text={letter.text} players={view.state.players} />”</p>
      <form method="dialog"><button class="primary">Dismiss</button></form>
    </dialog>
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
          <span><i class="swatch" style:background={colorOf(country.owner)}></i> {country.name}</span>
          <small class="muted">{isOwner && country.owner === playback.human ? 'you' : nameOf(country.owner)}</small>
          <b>{country.soldiers}</b>
        </button>
      {/each}
    </section>

    <Feed title="Commentary" size={feed.length}>
      {#each feed as note}
        {#if note}
          <li class={note.kind}>
            {#if note.kind === 'advice'}
              {@render advised(note)}
            {:else if note.kind === 'letter'}
              <Named text="{nameOf(note.player)}: “{note.text}”" players={view.state.players} />
            {:else}
              <Named text={note.text} players={view.state.players} />
            {/if}
          </li>
        {:else}
          <li class="muted gap" title="No commentary was written for these battles">. . .</li>
        {/if}
      {:else}
        <li class="muted">No commentary.</li>
      {/each}
    </Feed>

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
  }

  .copy {
    min-width: 7em;
  }

  .letter {
    font-style: italic;
  }

  dialog {
    width: min(28rem, 100vw - 2rem);
    padding: 0.9rem 1.1rem;
    color: var(--ink);
    background: var(--panel);
    border: 1px solid var(--ink);
  }

  dialog::backdrop {
    background: rgb(43 34 25 / 0.35);
  }

  dialog h2 {
    font-size: inherit;
    font-weight: 700;
  }

  dialog p {
    font-size: 18px;
    font-style: italic;
  }

  dialog form {
    margin-top: 0.75rem;
    text-align: right;
  }

  div.advice {
    margin-top: 0.5rem;
  }

  .gap {
    text-align: center;
  }

  blockquote {
    margin: 0.25rem 0 0;
    padding-left: 0.6rem;
    border-left: 2px solid var(--ink);
  }

  .board {
    grid-area: board;
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

  .sides span,
  .countries span {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .sides b {
    text-align: right;
  }

  .title {
    display: flex;
    flex-wrap: wrap;
    justify-content: space-between;
    align-items: baseline;
    column-gap: 1rem;
  }

  .panel h2 {
    margin: 0 0 0.25rem;
    font-size: inherit;
    font-weight: 700;
  }

  .panel .result {
    font-size: 20px;
  }

  input[type='number'] {
    width: 4.5rem;
  }

  .speed {
    align-self: flex-end;
    min-width: 13em;
    margin-top: 0.5rem;
  }

  p.line {
    display: none;
  }

  .replay {
    grid-area: replay;
    display: flex;
    gap: 0.5rem;
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
    min-width: 6em;
    text-align: right;
  }

  aside {
    grid-area: aside;
    display: grid;
    grid-template-rows: auto minmax(8rem, 2fr) minmax(8rem, 3fr);
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

  @media (max-width: 800px), (max-height: 500px) {
    .layout {
      grid-template-columns: minmax(0, 1fr);
      grid-template-rows: auto max(40dvh, 16rem);
      grid-template-areas:
        'header'
        'board'
        'replay'
        'panel'
        'aside';
      height: auto;
    }

    .panel {
      grid-area: panel;
      width: 100%;
      min-height: 10rem;
      margin: 0;
      border-width: 1px 0 0;
    }

    .title {
      order: -3;
    }

    fieldset {
      order: -2;
    }

    .speed {
      order: -1;
    }

    p.line {
      display: block;
    }

    .fight,
    .replay {
      flex-wrap: wrap;
    }

    .replay input {
      order: 1;
      flex-basis: 100%;
    }

    .replay span {
      flex: 1;
    }

    .sides {
      width: 100%;
    }

    aside {
      grid-template-rows: none;
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
  }
</style>
