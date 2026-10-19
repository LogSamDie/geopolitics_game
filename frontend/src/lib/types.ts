// Mirrors the Pydantic models in backend/app/engine.py and games.py.

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

export type Pair = [attacker: number, defender: number]

export interface GameEvent {
  seq: number
  kind: Kind
  text: string
  reason: string | null
  dice: Pair[] | null
  countries: Country[]
  turn: Turn
}

export interface State {
  players: Player[]
  countries: Country[]
  turn: Turn
  seq: number
}

export interface GameView {
  id: string
  owner: string
  state: State
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

export interface CountryInfo {
  code: string
  name: string
  population: number
  value: number
}

export type Command =
  | { kind: 'reinforce'; country: string; soldiers: number }
  | { kind: 'transfer'; source: string; target: string; soldiers: number }
  | { kind: 'attack'; source: string; target: string }
  | { kind: 'roll' }
  | { kind: 'stop' }
  | { kind: 'end_turn' }
