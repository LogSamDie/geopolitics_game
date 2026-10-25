import type { GameEvent, GameView, Player } from './types'

/**
 * What the viewer sees: the board after the first `shown` of all known events. New events are
 * revealed one at a time with a pause, which is what makes battles and NPC turns watchable, and
 * moving `shown` back replays a finished game.
 */
export class Playback {
  readonly players: Player[]
  events = $state<GameEvent[]>([])
  shown = $state(0)
  fast = $state(false)
  private timer = $state<ReturnType<typeof setTimeout>>()

  readonly log = $derived(this.events.slice(0, this.shown))
  // The first event lists every country; each later one lists those it changed.
  readonly countries = $derived(Object.fromEntries(this.log.flatMap((e) => e.countries).map((c) => [c.code, c])))

  constructor(view: GameView) {
    this.players = view.state.players
    this.events = view.events
    // Everything up to the player's last own move is shown at once; what followed is played out.
    // So a new game plays from the beginning, and a reload replays the NPC turns since. A finished
    // game opens at its end, unless the player was out before ever moving and has yet to see it.
    const human = view.state.players.find((p) => !p.npc)
    const lastMove = view.events.findLastIndex((e) => e.turn.player === human?.id && e.kind !== 'turn')
    this.shown = this.over && lastMove >= 0 ? view.events.length : Math.max(1, lastMove + 1)
    this.play()
  }

  get seq(): number {
    return this.events.at(-1)?.seq ?? 0
  }

  get busy(): boolean {
    return this.shown < this.events.length
  }

  get over(): boolean {
    return this.events.at(-1)?.turn.phase === 'over'
  }

  /** Events are being revealed one after another. */
  get playing(): boolean {
    return this.running && this.busy
  }

  /** A pause is under way, including the one after the newest event. */
  get running(): boolean {
    return this.timer !== undefined
  }

  add(events: GameEvent[]): void {
    const fresh = events.filter((e) => e.seq > this.seq)
    // A batch that skips ahead (another device moved) waits for the poll, which brings all of it.
    if (fresh[0]?.seq !== this.seq + 1) return
    this.events.push(...fresh)
    this.play()
  }

  play(): void {
    if (this.timer === undefined) this.step()
  }

  pause(): void {
    clearTimeout(this.timer)
    this.timer = undefined
  }

  /** The replay button: stop a running replay, else go on from here, or from the top at the end. */
  toggle(): void {
    const stopping = this.playing
    this.pause()
    if (stopping) return
    if (!this.busy) this.shown = 0
    this.play()
  }

  /** Change speed, applied to the pause under way. */
  toggleSpeed(): void {
    this.fast = !this.fast
    const current = this.events[this.shown - 1]
    if (this.running && current) this.wait(current)
  }

  private step(): void {
    const event = this.events[this.shown]
    if (event === undefined) {
      this.timer = undefined
      this.fast = false // fast-forward lasts until everything has been shown
      return
    }
    this.shown += 1
    this.wait(event)
  }

  private wait(event: GameEvent): void {
    clearTimeout(this.timer)
    this.timer = setTimeout(() => this.step(), this.delay(event))
  }

  private delay(event: GameEvent): number {
    if (this.fast) return this.over ? 75 : 150 // a finished game has no next turn to wait for
    if (event.kind === 'rolled' || event.kind === 'transferred') return 1500
    if (event.reason !== null) return 2000 // time to read an NPC's reasoning
    return 700
  }
}
