import Markdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import type { Role } from '../api'

interface Props {
  role: Role
  content: string
  pending?: boolean
}

export function MessageBubble({ role, content, pending }: Props) {
  return (
    <div className={`msg msg--${role}`}>
      <div className="msg__bubble">
        {role === 'assistant' ? (
          content ? (
            <div className="markdown">
              <Markdown remarkPlugins={[remarkGfm]}>{content}</Markdown>
            </div>
          ) : (
            <span className="typing" aria-label="Assistant is typing">
              <span />
              <span />
              <span />
            </span>
          )
        ) : (
          <p className="msg__text">{content}</p>
        )}
        {pending && content && <span className="cursor" aria-hidden="true" />}
      </div>
    </div>
  )
}
