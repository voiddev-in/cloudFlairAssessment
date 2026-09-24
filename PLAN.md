# Project Plan — AI Chat Assistant on Cloudflare (Python · React · MongoDB)

## 0. Requirements recap (from README)

| # | Required component | How we satisfy it |
|---|---|---|
| 1 | **LLM** | Llama 3.3 70B on **Workers AI** (`@cf/meta/llama-3.3-70b-instruct-fp8-fast`) via the `AI` binding |
| 2 | **Workflow / coordination** | **Durable Object** per chat session (live coordination) + **Cloudflare Workflow** for multi-step background jobs |
| 3 | **User input via chat/voice** | **React** chat UI deployed on **Cloudflare Pages** (voice = stretch goal) |
| 4 | **Memory / state** | Short-term: Durable Object storage. Long-term: **MongoDB Atlas** |
| — | **Submission** | Public repo, `README.md` with run/deploy steps + live URL, `PROMPTS.md` with AI prompt history |

**Deadline:** this weekend (Sun 27 Sep 2026). Scope is chosen to be finished and polished in ~3 days, not maximal.

### Product idea (swappable)
**"Study Buddy"** — a chat assistant that remembers what you are learning. You chat normally; it remembers facts about you
("I'm preparing for a Python interview") across sessions, and you can ask it to *"make me a study plan"*, which runs as
a multi-step Workflow (outline → expand → quiz) and posts the result back into the chat.
This naturally exercises all four components. Any other domain works with the same architecture.

---

## 1. Architecture

```
 React (Vite + TS)  ──WebSocket/HTTP──►  Python Worker (FastAPI, Cloudflare)
 Cloudflare Pages                          │
                                           ├─► ChatSession Durable Object (1 per session)
                                           │     • live message window (DO storage)
                                           │     • calls Workers AI (Llama 3.3), streams tokens
                                           │
                                           ├─► StudyPlan Workflow (durable multi-step job)
                                           │     outline → expand → quiz → notify DO
                                           │
                                           └─► Memory Service (HTTPS, API key)
                                                 FastAPI + Motor on Render/Fly
                                                 └─► MongoDB Atlas
                                                       users, sessions, messages, memories
```

### Key technical decisions (and why)

1. **Python on Cloudflare Workers (FastAPI)** for the edge API, DO and Workflow. Keeps the backend in Python while still
   using Cloudflare primitives, which is the point of the assignment.
2. **MongoDB lives behind a small separate FastAPI "memory service".** Python Workers run on Pyodide and cannot open the
   raw TCP connection `pymongo`/`motor` need, and the Atlas Data API is gone. So Mongo is reached through a
   thin HTTPS service. It also keeps a clean boundary: Cloudflare is where compute and coordination happen; Mongo is the
   system of record.
   - *Simpler alternative:* drop Mongo and use Durable Object storage / D1 for everything. Fewer moving parts and
     more Cloudflare-native. Decide in Phase 0.
3. **One Durable Object per chat session** gives ordering, a single writer, and WebSocket fan-out with no locking.
4. **Workflows only for long or multi-step work** (study plan). Normal chat turns stay in the DO for low latency.
5. **Fallback:** if Python Workers can't do something we need (DO WebSockets, Workflows bindings, a package), the edge
   layer is rewritten in TypeScript. Python stays in the memory service. The Phase 0 spike checks this first.

### Repo layout

```
/frontend          React + Vite + TS (Cloudflare Pages)
/edge              Python Worker: FastAPI app, ChatSession DO, StudyPlan Workflow, wrangler.toml
/memory-service    FastAPI + Motor + Pydantic, Dockerfile
/docs              architecture diagram, API contract
PLAN.md  PROMPTS.md  README.md
```

---

## 2. Phases

Each phase ends with something that runs and a commit. Don't start a phase until the previous exit criteria pass.

### Phase 0: Spike & setup (Thu evening, ~2–3h). *De-risk before building*
- [ ] Cloudflare account, `wrangler login`, MongoDB Atlas free cluster, Render/Fly account.
- [ ] Start `PROMPTS.md` **now** and log every AI prompt as you go (required for submission).
- [ ] Throwaway Python Worker proving: (a) the `AI` binding returns a Llama 3.3 completion, (b) a Python Durable Object
      persists a counter, (c) a Python Workflow runs 2 steps. **This is the go/no-go for Python on the edge.**
- [ ] Decide: Mongo via memory service (default) vs DO/D1-only.
- [ ] Create the monorepo skeleton, `.gitignore`, `.env.example`, pre-commit (ruff, black, prettier, eslint).

**Exit:** all three spike checks pass (or the fallback is chosen), skeleton committed.

### Phase 1: Memory service + MongoDB (Fri morning, ~3h)
- [ ] FastAPI app with Pydantic v2 models; Motor async client; settings via `pydantic-settings`.
- [ ] Collections and indexes:
  - `users { _id, created_at }`
  - `sessions { _id, user_id, title, created_at, updated_at }`, index `(user_id, updated_at)`
  - `messages { _id, session_id, role, content, created_at }`, index `(session_id, created_at)`
  - `memories { _id, user_id, fact, source_session_id, created_at }`, index `(user_id)`
- [ ] Endpoints: `POST/GET /sessions`, `POST/GET /sessions/{id}/messages`, `GET/POST/DELETE /users/{id}/memories`,
      `GET /healthz`.
- [ ] Auth: shared `X-API-Key` between edge and memory service (secret in both envs).
- [ ] Tests: pytest + httpx `AsyncClient` against `mongomock-motor` or a test DB.
- [ ] Dockerfile; deploy to Render/Fly; Atlas IP allowlist / connection string as a secret.

**Exit:** deployed `/healthz` is green; can create a session and add/read messages with curl.

### Phase 2: Edge chat core (Fri afternoon, ~4h)
- [ ] `edge/` Python Worker with FastAPI routes: `POST /api/sessions`, `GET /api/sessions/{id}/ws` (upgrade → DO).
- [ ] `ChatSession` Durable Object:
  - accepts WebSocket, keeps last N messages in DO storage (short-term memory),
  - builds prompt = system prompt + user long-term memories (from memory service) + recent window + new message,
  - calls Workers AI with `stream=True` and forwards tokens over the WebSocket,
  - write-behind persists user and assistant messages to the memory service (failures don't block the chat reply).
- [ ] Message protocol (JSON): `{type: "user_msg" | "token" | "done" | "error" | "workflow_update", ...}`.
- [ ] Token budget: trim the context window by an approximate token count; cap `max_tokens`.
- [ ] Local dev with `wrangler dev`; memory service URL/key as Worker secrets.

**Exit:** with `wscat`, send a message and get a streamed Llama reply; messages appear in Mongo.

### Phase 3: React frontend (Fri evening → Sat morning, ~4h)
- [ ] Vite + React + TypeScript; Tailwind (or plain CSS modules) for speed.
- [ ] Components: `SessionSidebar`, `ChatWindow`, `MessageBubble` (markdown rendering), `Composer`, `MemoryPanel`.
- [ ] `useChatSocket` hook: connect, reconnect with backoff, append streaming tokens, handle `error`.
- [ ] Anonymous user id stored in `localStorage` (no auth, which is fine for the assignment; mention it in the README).
- [ ] Loading, empty, and error states; stop-generation button.
- [ ] Deploy to Cloudflare Pages; configure `VITE_API_BASE`; CORS on the edge.

**Exit:** a public Pages URL where you can hold a streamed conversation and reload without losing history.

### Phase 4: Long-term memory (Sat midday, ~3h)
- [ ] After each assistant turn, the DO asks Llama (small JSON-mode prompt) to extract durable user facts, then dedupes and
      stores them via the memory service. Run it with `ctx.waitUntil` so it doesn't add latency.
- [ ] Inject the top-K memories into the system prompt (simple recency first; optional: Vectorize/embeddings for relevance).
- [ ] `MemoryPanel` in the UI: view and delete what the assistant remembers (good demo + privacy story).
- [ ] Session auto-title from the first exchange.

**Exit:** tell it a fact in session A; in a new session B it uses that fact unprompted.

### Phase 5: Workflow, multi-step job (Sat afternoon, ~3h)
- [ ] `StudyPlanWorkflow` with durable steps: `outline` → `expand_each_topic` → `generate_quiz` → `save_and_notify`.
      Each step calls Workers AI and has retries/timeouts configured.
- [ ] Trigger: the LLM decides via a lightweight intent check (or a `/plan <topic>` command as the dependable path).
- [ ] Progress: the workflow posts `workflow_update` events to the session DO, and the DO pushes them over the WebSocket.
      The UI shows a progress card.
- [ ] Final plan saved to Mongo and rendered as a rich message.

**Exit:** `/plan Python interviews` shows live step progress and ends with a stored, rendered plan.

### Phase 6: Hardening (Sat evening, ~2–3h)
- [ ] Input validation (message length limits), simple per-session rate limit in the DO.
- [ ] Error paths: LLM failure → friendly error event; memory service down → chat still works (degraded, logged).
- [ ] Secrets only via `wrangler secret` / platform env; nothing committed. Lock CORS to the Pages domain.
- [ ] Structured logging (`request_id`, `session_id`) in the edge and memory service.
- [ ] Tests: memory-service unit/API tests; edge prompt-builder and trimming as pure-function tests;
      one Playwright smoke test (send message → see reply) if time allows.
- [ ] GitHub Actions: lint + test on PR; optional auto-deploy.

**Exit:** CI green; kill the memory service and chat still replies.

### Phase 7: Docs, demo, submission (Sun, ~3h)
- [ ] `README.md`: what it is, live URL, architecture diagram, how each required component is met (the table above),
      local setup (`wrangler dev`, `uvicorn`, `npm run dev`), deploy steps, env vars, known limitations.
- [ ] `PROMPTS.md`: cleaned-up prompt history, grouped by phase.
- [ ] 2–3 minute demo video/GIF: chat → memory recall in a new session → study-plan workflow.
- [ ] Final pass: remove dead code, check the fresh-clone setup works end to end, tag `v1.0`.

**Exit:** a stranger can clone, read the README, and understand/run it in 10 minutes.

### Stretch (only if everything above is done)
- Voice input: browser Web Speech API → text (cheap), or Workers AI Whisper for server-side STT.
- Vectorize-backed semantic memory retrieval.
- Real auth (Cloudflare Access or magic-link).

---

## 3. Risks & mitigations

| Risk | Likelihood | Mitigation |
|---|---|---|
| Python Workers missing a feature (DO WebSockets, Workflows, a package) | Medium | Phase 0 spike; fallback to a TypeScript edge, Python kept in the memory service |
| Extra latency from the Worker → memory service hop | Medium | Fetch memories once per turn and cache in the DO; write-behind for persistence |
| Workers AI rate limits / cold model latency | Low–Med | Streaming, `max_tokens` cap, retry with backoff, fallback to the 8B model |
| Running out of time | Medium | Phases are ordered so that after Phase 3 there is already a submittable app |
| Leaked secrets | Low | `.env.example` only, `wrangler secret`, pre-commit secret scan |

## 4. Definition of done
- Live URL works: chat streams, history persists, memory carries across sessions, workflow runs with progress.
- All four README components are clearly visible in the code and explained in the README.
- `PROMPTS.md` included; repo is clean, linted, and tested; setup reproducible from a fresh clone.
