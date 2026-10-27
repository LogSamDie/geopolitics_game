import type { GameEvent, GameView } from './types'

/** The board after the first `shown` of the events, revealed one at a time with a pause. */
export class Playback {
  readonly human: string
  events = $state<GameEvent[]>([])
  shown = $state(0)
  fast = $state(false)
  private timer = $state<ReturnType<typeof setTimeout>>()

  readonly log = $derived(this.events.slice(0, this.shown))
  // The first event lists every country, later ones those they changed.
  readonly countries = $derived(Object.fromEntries(this.log.flatMap((e) => e.countries).map((c) => [c.code, c])))

  constructor(view: GameView) {
    this.human = view.state.players.find((p) => !p.npc)!.id
    this.events = view.events
    // Show at once up to the player's last move and play out the rest. A finished game opens at
    // its end, unless the player was out before ever moving and has yet to see what happened.
    const lastMove = view.events.findLastIndex((e) => e.turn.player === this.human && e.kind !== 'turn')
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

  pause(): void {
    clearTimeout(this.timer)
    this.timer = undefined
  }

  /** Stop a running replay, else go on from here, or from the top at the end. */
  toggle(): void {
    const stopping = this.playing
    this.pause()
    if (stopping) return
    if (!this.busy) this.shown = 0
    this.play()
  }

  toggleSpeed(): void {
    this.fast = !this.fast
    if (this.running) this.wait(this.events[this.shown - 1])
  }

  private play(): void {
    if (!this.running) this.step()
  }

  private step(): void {
    if (this.busy) {
      this.wait(this.events[this.shown++])
    } else {
      this.timer = undefined
      this.fast = false
    }
  }

  private wait(event: GameEvent): void {
    clearTimeout(this.timer)
    this.timer = setTimeout(() => this.step(), this.delay(event))
  }

  private delay(event: GameEvent): number {
    if (this.fast) return this.over ? 75 : 150
    if (event.kind === 'rolled' || event.kind === 'transferred') return 1500
    if (event.reason !== null) return 2000
    return 700
  }
}
