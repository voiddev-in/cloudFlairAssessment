const KEY = 'study-buddy:user-id'

/** Anonymous per-browser user id. Falls back to an in-memory id if storage is blocked. */
export function getUserId(): string {
  try {
    const existing = localStorage.getItem(KEY)
    if (existing) return existing
    const id = crypto.randomUUID()
    localStorage.setItem(KEY, id)
    return id
  } catch {
    return crypto.randomUUID()
  }
}
