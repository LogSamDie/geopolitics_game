import type { Player } from './types'

// Hand-tinted atlas washes. The human is always carmine; the NPCs take the rest in turn order.
const PALETTE = [
  '#a4343e',
  '#dcbd6b',
  '#a9bb8e',
  '#9dbdd6',
  '#b9a3d6',
  '#e9b48a',
  '#8fc2b4',
  '#dca0ae',
  '#ad8862',
  '#b5a893',
]

export function colorOf(players: Player[], playerId: string): string {
  const player = players.find((p) => p.id === playerId)
  const index = player?.npc ? 1 + players.filter((p) => p.npc).indexOf(player) : 0
  return PALETTE[index] ?? '#777'
}

/** Text that stays legible on an owner colour: paper on carmine, ink on every wash. */
export const textOn = (color: string): string => (color === PALETTE[0] ? 'var(--panel)' : 'var(--ink)')
