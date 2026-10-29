export type Phase = 'reinforce' | 'action' | 'attack' | 'over'

export type Kind =
  | 'started'
  | 'turn'
  | 'reinforced'
  | 'transferred'
  | 'attacked'
  | 'rolled'
  | 'conquered'
  | 'repelled'
  | 'stopped'
  | 'skipped'
  | 'eliminated'
  | 'over'

export interface Player {
  id: string
  name: string
  npc: boolean
}

export interface Country {
  code: string
  name: string
  value: number
  owner: string
  soldiers: number
}

export interface Turn {
  player: string
  round: number
  phase: Phase
  reinforcements: number
  attack: { source: string; target: string } | null
  winner: string | null
}

export interface GameEvent {
  seq: number
  kind: Kind
  text: string
  reason: string | null
  dice: [attacker: number, defender: number][] | null
  countries: Country[]
  turn: Turn
}

export interface GameView {
  id: string
  owner: string
  state: { players: Player[] }
  events: GameEvent[]
}

export interface GameSummary {
  id: string
  created: string
  human: string
  country: string
  turn: Turn
  countries: number
}

export interface User {
  id: string
  username: string
}

export interface Route {
  source: string
  target: string
  attack: boolean
  live: boolean
}

export type Command =
  | { kind: 'reinforce'; country: string; soldiers: number }
  | { kind: 'transfer'; source: string; target: string; soldiers: number }
  | { kind: 'attack'; source: string; target: string }
  | { kind: 'roll' }
  | { kind: 'fight' }
  | { kind: 'stop' }
  | { kind: 'end_turn' }
