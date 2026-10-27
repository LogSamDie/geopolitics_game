// Player ids are p0, the human, to p9.
const palette = [
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

export const colorOf = (playerId: string): string => palette[Number(playerId.slice(1))]

export const textOn = (color: string): string => (color === palette[0] ? 'var(--panel)' : 'var(--ink)')
