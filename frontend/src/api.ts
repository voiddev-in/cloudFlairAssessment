export const API_BASE = (import.meta.env.VITE_API_BASE ?? 'http://localhost:8787').replace(/\/$/, '')

export type Role = 'user' | 'assistant'

export interface ChatMessage {
  id: string
  role: Role
  content: string
}

export interface Session {
  id: string
  title: string
  updated_at?: string
}

/** Events pushed by the ChatSession Durable Object over the WebSocket. */
export type ServerEvent =
  | { type: 'token'; content: string }
  | { type: 'done'; content: string }
  | { type: 'error'; content: string }

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...init?.headers },
  })
  if (!res.ok) throw new Error(`${init?.method ?? 'GET'} ${path} failed: ${res.status}`)
  return res.json() as Promise<T>
}

export async function listSessions(userId: string): Promise<Session[]> {
  const data = await request<{ sessions: Session[] }>(`/api/sessions?user_id=${encodeURIComponent(userId)}`)
  return data.sessions
}

export function createSession(userId: string): Promise<Session> {
  return request<Session>('/api/sessions', { method: 'POST', body: JSON.stringify({ user_id: userId }) })
}

export async function getMessages(sessionId: string): Promise<ChatMessage[]> {
  const data = await request<{ messages: ChatMessage[] }>(`/api/sessions/${sessionId}/messages`)
  return data.messages
}

export function wsUrl(sessionId: string): string {
  return `${API_BASE.replace(/^http/, 'ws')}/api/sessions/${sessionId}/ws`
}
