import { useEffect, useRef } from 'react'
import { useChat, type ConnectionStatus } from '../useChat'
import { Composer } from './Composer'
import { MessageBubble } from './MessageBubble'

const SUGGESTIONS = [
  'Explain recursion with a simple example',
  'Quiz me on Python list comprehensions',
  'What is the difference between TCP and UDP?',
]

const STATUS_LABEL: Record<ConnectionStatus, string> = {
  idle: '',
  connecting: 'Connecting…',
  open: '',
  reconnecting: 'Connection lost, reconnecting…',
}

interface Props {
  sessionId: string
  onReply: () => void
}

export function ChatView({ sessionId, onReply }: Props) {
  const { messages, streaming, status, error, send: onSend } = useChat(sessionId, onReply)
  const endRef = useRef<HTMLDivElement>(null)
  const busy = streaming !== null
  const ready = status === 'open'

  useEffect(() => {
    endRef.current?.scrollIntoView({ block: 'end' })
  }, [messages, streaming])

  return (
    <section className="chat">
      <div className="chat__scroll">
        <div className="chat__inner">
          {messages.length === 0 && !busy ? (
            <div className="welcome">
              <h1>What are you learning today?</h1>
              <p>Ask a question, or pick one to get started.</p>
              <div className="welcome__chips">
                {SUGGESTIONS.map((s) => (
                  <button key={s} type="button" className="chip" disabled={!ready} onClick={() => onSend(s)}>
                    {s}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            messages.map((m) => <MessageBubble key={m.id} role={m.role} content={m.content} />)
          )}
          {busy && <MessageBubble role="assistant" content={streaming} pending />}
          <div ref={endRef} />
        </div>
      </div>

      <div className="chat__footer">
        {(error || STATUS_LABEL[status]) && (
          <p className={`notice${error ? ' notice--error' : ''}`} role="status">
            {error ?? STATUS_LABEL[status]}
          </p>
        )}
        <Composer
          disabled={!ready || busy}
          placeholder={busy ? 'Study Buddy is answering…' : 'Ask Study Buddy anything…'}
          onSend={onSend}
        />
      </div>
    </section>
  )
}
