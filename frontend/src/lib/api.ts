import type { Command, Country, GameSummary, GameView, User } from './types'

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const response = await fetch(path, {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!response.ok) {
    const { detail } = await response.json().catch(() => ({}))
    throw new Error(typeof detail === 'string' ? detail : `Request failed (${response.status})`)
  }
  return response.status === 204 ? (undefined as T) : response.json()
}

export const message = (e: unknown): string => (e instanceof Error ? e.message : String(e))

export const api = {
  me: () => request<User>('GET', '/api/auth/me'),
  register: (username: string, password: string) => request<User>('POST', '/api/auth/register', { username, password }),
  login: (username: string, password: string) => request<User>('POST', '/api/auth/login', { username, password }),
  logout: () => request<void>('POST', '/api/auth/logout'),
  countries: () => request<Country[]>('GET', '/api/countries'),
  games: () => request<GameSummary[]>('GET', '/api/games'),
  createGame: (country: string) => request<GameView>('POST', '/api/games', { country }),
  game: (id: string, after = 0) => request<GameView>('GET', `/api/games/${id}?after=${after}`),
  play: (id: string, command: Command) => request<GameView>('POST', `/api/games/${id}/commands`, command),
  advice: (id: string) => request<GameView>('POST', `/api/games/${id}/advice`),
}
