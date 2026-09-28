import { useCallback, useEffect, useRef, useState } from 'react'
import { createSession, listSessions, type Session } from './api'
import { ChatView } from './components/ChatView'
import { Sidebar } from './components/Sidebar'
import { getUserId } from './userId'
import './App.css'

function App() {
  const [userId] = useState(getUserId)
  const [sessions, setSessions] = useState<Session[]>([])
  const [activeId, setActiveId] = useState<string | null>(null)
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [loadError, setLoadError] = useState<string | null>(null)
  const initialized = useRef(false)

  const refreshSessions = useCallback(() => {
    listSessions(userId)
      .then(setSessions)
      .catch(() => {})
  }, [userId])

  // On first load, open the most recent chat, or create one for a new user.
  useEffect(() => {
    if (initialized.current) return
    initialized.current = true
    ;(async () => {
      try {
        let list = await listSessions(userId)
        if (list.length === 0) list = [await createSession(userId)]
        setSessions(list)
        setActiveId(list[0].id)
      } catch {
        setLoadError('Cannot reach the Study Buddy API. Is the edge worker running?')
      }
    })()
  }, [userId])

  const newChat = async () => {
    try {
      const session = await createSession(userId)
      setSessions((prev) => [session, ...prev])
      setActiveId(session.id)
      setSidebarOpen(false)
    } catch {
      setLoadError('Could not create a new chat.')
    }
  }

  const selectChat = (id: string) => {
    setActiveId(id)
    setSidebarOpen(false)
  }

  return (
    <div className="app">
      <Sidebar sessions={sessions} activeId={activeId} open={sidebarOpen} onSelect={selectChat} onNew={newChat} />
      {sidebarOpen && <div className="scrim" onClick={() => setSidebarOpen(false)} aria-hidden="true" />}

      <main className="main">
        <header className="topbar">
          <button type="button" className="btn btn--ghost topbar__menu" onClick={() => setSidebarOpen(true)}>
            ☰ Chats
          </button>
          <span className="topbar__title">{sessions.find((s) => s.id === activeId)?.title ?? 'Study Buddy'}</span>
        </header>

        {loadError ? (
          <div className="fatal" role="alert">
            {loadError}
          </div>
        ) : (
          activeId && <ChatView key={activeId} sessionId={activeId} onReply={refreshSessions} />
        )}
      </main>
    </div>
  )
}

export default App
