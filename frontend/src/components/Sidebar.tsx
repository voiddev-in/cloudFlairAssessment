import type { Session } from '../api'

interface Props {
  sessions: Session[]
  activeId: string | null
  open: boolean
  onSelect: (id: string) => void
  onNew: () => void
}

export function Sidebar({ sessions, activeId, open, onSelect, onNew }: Props) {
  return (
    <aside className={`sidebar${open ? ' sidebar--open' : ''}`}>
      <div className="sidebar__brand">
        <span className="sidebar__logo" aria-hidden="true">
          SB
        </span>
        Study Buddy
      </div>
      <button type="button" className="btn btn--primary sidebar__new" onClick={onNew}>
        + New chat
      </button>
      <nav className="sidebar__list" aria-label="Chat sessions">
        {sessions.length === 0 && <p className="sidebar__empty">No chats yet</p>}
        {sessions.map((s) => (
          <button
            key={s.id}
            type="button"
            className={`sidebar__item${s.id === activeId ? ' sidebar__item--active' : ''}`}
            onClick={() => onSelect(s.id)}
            title={s.title}
          >
            {s.title}
          </button>
        ))}
      </nav>
      <p className="sidebar__footer">Llama 3.3 · Workers AI</p>
    </aside>
  )
}
