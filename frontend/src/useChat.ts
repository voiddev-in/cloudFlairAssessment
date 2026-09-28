import { useCallback, useEffect, useRef, useState } from 'react'
import { getMessages, wsUrl, type ChatMessage, type ServerEvent } from './api'

export type ConnectionStatus = 'idle' | 'connecting' | 'open' | 'reconnecting'

const MAX_BACKOFF_MS = 15_000

/**
 * Loads a session's history and keeps a WebSocket open to its ChatSession Durable Object.
 * `streaming` is null when idle, or the partial assistant reply while tokens arrive.
 * Mount with `key={sessionId}` so switching sessions starts from fresh state.
 */
export function useChat(sessionId: string, onReply?: () => void) {
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [streaming, setStreaming] = useState<string | null>(null)
  const [status, setStatus] = useState<ConnectionStatus>('idle')
  const [error, setError] = useState<string | null>(null)
  const wsRef = useRef<WebSocket | null>(null)
  const onReplyRef = useRef(onReply)

  useEffect(() => {
    onReplyRef.current = onReply
  }, [onReply])

  useEffect(() => {
    let cancelled = false
    let attempt = 0
    let timer: number | undefined

    getMessages(sessionId)
      .then((history) => {
        if (!cancelled) setMessages(history)
      })
      .catch(() => {
        if (!cancelled) setError('Could not load chat history.')
      })

    const connect = () => {
      setStatus(attempt === 0 ? 'connecting' : 'reconnecting')
      const ws = new WebSocket(wsUrl(sessionId))
      wsRef.current = ws

      ws.onopen = () => {
        attempt = 0
        setStatus('open')
      }
      ws.onmessage = (event) => {
        const msg = JSON.parse(event.data) as ServerEvent
        if (msg.type === 'token') {
          setStreaming((partial) => (partial ?? '') + msg.content)
        } else if (msg.type === 'done') {
          setStreaming(null)
          setMessages((prev) => [...prev, { id: crypto.randomUUID(), role: 'assistant', content: msg.content }])
          onReplyRef.current?.()
        } else if (msg.type === 'error') {
          setStreaming(null)
          setError(msg.content)
        }
      }
      ws.onclose = () => {
        if (cancelled) return
        setStreaming(null)
        attempt += 1
        setStatus('reconnecting')
        timer = window.setTimeout(connect, Math.min(1000 * 2 ** attempt, MAX_BACKOFF_MS))
      }
    }

    connect()
    return () => {
      cancelled = true
      window.clearTimeout(timer)
      wsRef.current?.close()
      wsRef.current = null
    }
  }, [sessionId])

  const send = useCallback((content: string): boolean => {
    const ws = wsRef.current
    const text = content.trim()
    if (!text || !ws || ws.readyState !== WebSocket.OPEN) return false
    setError(null)
    setMessages((prev) => [...prev, { id: crypto.randomUUID(), role: 'user', content: text }])
    setStreaming('')
    ws.send(JSON.stringify({ type: 'user_msg', content: text }))
    return true
  }, [])

  return { messages, streaming, status, error, send }
}
