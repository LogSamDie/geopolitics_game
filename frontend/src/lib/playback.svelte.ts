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
  private timer: ReturnType<typeof setTimeout> | undefined

  readonly log = $derived(this.events.slice(0, this.shown))
  // The first event lists every country; each later one lists those it changed.
  readonly countries = $derived(Object.fromEntries(this.log.flatMap((e) => e.countries).map((c) => [c.code, c])))

  constructor(view: GameView) {
    this.players = view.state.players
    this.events = view.events
    // Everything up to the player's last own move is shown at once; what followed is played out.
    // So a new game plays from the beginning, and a reload replays the NPC turns since.
    const human = view.state.players.find((p) => !p.npc)
    const lastMove = view.events.findLastIndex((e) => e.turn.player === human?.id && e.kind !== 'turn')
    this.shown = this.over ? view.events.length : Math.max(1, lastMove + 1)
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

  add(events: GameEvent[]): void {
    const fresh = events.filter((e) => e.seq > this.seq)
    if (fresh.length === 0) return
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

  replay(): void {
    this.shown = 1
    this.play()
  }

  private step(): void {
    const event = this.events[this.shown]
    if (event === undefined) {
      this.timer = undefined
      return
    }
    this.shown += 1
    this.timer = setTimeout(() => this.step(), this.delay(event))
  }

  private delay(event: GameEvent): number {
    if (this.fast) return 150
    if (event.kind === 'rolled') return 1500
    if (event.reason !== null) return 2000 // time to read an NPC's reasoning
    return 700
  }
}
