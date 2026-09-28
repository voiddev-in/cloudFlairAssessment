import { useState, type FormEvent, type KeyboardEvent } from 'react'

const MAX_CHARS = 4000

interface Props {
  disabled: boolean
  placeholder: string
  onSend: (text: string) => boolean
}

export function Composer({ disabled, placeholder, onSend }: Props) {
  const [text, setText] = useState('')
  const canSend = !disabled && text.trim().length > 0 && text.length <= MAX_CHARS

  const submit = (e?: FormEvent) => {
    e?.preventDefault()
    if (canSend && onSend(text)) setText('')
  }

  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault()
      submit()
    }
  }

  return (
    <form className="composer" onSubmit={submit}>
      <textarea
        className="composer__input"
        value={text}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={onKeyDown}
        placeholder={placeholder}
        rows={1}
        maxLength={MAX_CHARS}
        aria-label="Message"
      />
      <button type="submit" className="btn btn--primary composer__send" disabled={!canSend}>
        Send
      </button>
    </form>
  )
}
