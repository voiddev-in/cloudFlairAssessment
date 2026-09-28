import codecs
import json
import re
import uuid
from urllib.parse import parse_qs, urlparse

from js import Object, WebSocketPair
from pyodide.ffi import to_js
from workers import DurableObject, Response, WorkerEntrypoint, WorkflowEntrypoint

MODEL = "@cf/meta/llama-3.3-70b-instruct-fp8-fast"
SYSTEM_PROMPT = (
    "You are Study Buddy, a friendly and concise tutor. "
    "Explain concepts clearly, use short examples, and format answers in Markdown."
)
MAX_MESSAGE_CHARS = 4000
HISTORY_WINDOW = 20  # messages kept in DO storage as short-term memory
MAX_TOKENS = 1024

SESSION_WS_RE = re.compile(r"^/api/sessions/([0-9a-f-]{36})/ws$")
SESSION_MESSAGES_RE = re.compile(r"^/api/sessions/([0-9a-f-]{36})/messages$")


def js_obj(value):
    """Convert a Python dict/list into plain JS objects/arrays (not Maps)."""
    return to_js(value, dict_converter=Object.fromEntries)


def rows(result):
    """Convert a D1 `.all()` result into a list of Python dicts."""
    return result.results.to_py() if result.results else []


class ChatSession(DurableObject):
    """One instance per chat session: owns the WebSocket and the short-term history."""

    def __init__(self, ctx, env):
        super().__init__(ctx, env)
        self.ctx = ctx
        self.env = env
        self.generating = False

    async def fetch(self, request):
        if request.headers.get("Upgrade") != "websocket":
            return Response("Expected Upgrade: websocket", status=426)

        match = SESSION_WS_RE.match(urlparse(request.url).path)
        if not match:
            return Response("Bad session id", status=400)
        await self.ctx.storage.put("session_id", match.group(1))

        client, server = WebSocketPair.new().object_values()
        # Hibernation API: the runtime calls webSocketMessage/webSocketClose for us.
        self.ctx.acceptWebSocket(server)
        return Response(None, status=101, web_socket=client)

    async def webSocketMessage(self, ws, message):
        try:
            data = json.loads(message)
        except (TypeError, ValueError):
            return self.send(ws, "error", "Invalid message format.")

        if data.get("type") != "user_msg":
            return self.send(ws, "error", "Unknown message type.")

        content = (data.get("content") or "").strip()
        if not content:
            return self.send(ws, "error", "Message is empty.")
        if len(content) > MAX_MESSAGE_CHARS:
            return self.send(ws, "error", f"Message is longer than {MAX_MESSAGE_CHARS} characters.")
        if self.generating:
            return self.send(ws, "error", "Still answering the previous message.")

        self.generating = True
        try:
            await self.handle_user_message(ws, content)
        except Exception as e:  # noqa: BLE001 - report any failure to the client
            print(f"chat error: {e!r}")
            self.send(ws, "error", "The assistant failed to respond. Please try again.")
        finally:
            self.generating = False

    async def webSocketClose(self, ws, code, reason, was_clean):
        try:
            ws.close(code, reason)
        except Exception:  # noqa: BLE001 - already closed, or a reserved code like 1005
            pass

    async def handle_user_message(self, ws, content):
        session_id = await self.ctx.storage.get("session_id")
        recent = await self.load_history()
        recent.append({"role": "user", "content": content})

        await self.save_message(session_id, "user", content)
        await self.env.DB.prepare(
            "UPDATE sessions SET title = CASE WHEN title = 'New Chat' THEN ? ELSE title END, "
            "updated_at = CURRENT_TIMESTAMP WHERE id = ?"
        ).bind(content[:60], session_id).run()

        messages = [{"role": "system", "content": SYSTEM_PROMPT}] + recent
        reply = await self.stream_completion(ws, messages)

        recent.append({"role": "assistant", "content": reply})
        await self.ctx.storage.put("messages", json.dumps(recent[-HISTORY_WINDOW:]))
        await self.save_message(session_id, "assistant", reply)
        self.send(ws, "done", reply)

    async def stream_completion(self, ws, messages):
        """Stream tokens from Workers AI to the client; return the full reply."""
        if getattr(self.env, "MOCK_AI", None) == "1":
            return self.mock_completion(ws, messages)

        stream = await self.env.AI.run(
            MODEL, js_obj({"messages": messages, "stream": True, "max_tokens": MAX_TOKENS})
        )
        reader = stream.getReader()
        decoder = codecs.getincrementaldecoder("utf-8")()
        buffer, reply = "", []

        while True:
            chunk = await reader.read()
            if chunk.done:
                break
            buffer += decoder.decode(chunk.value.to_bytes())
            # Server-sent events: each event is "data: {...}" terminated by a blank line.
            *events, buffer = buffer.split("\n\n")
            for event in events:
                payload = event.removeprefix("data:").strip()
                if not payload or payload == "[DONE]":
                    continue
                token = json.loads(payload).get("response") or ""
                if token:
                    reply.append(token)
                    self.send(ws, "token", token)

        return "".join(reply)

    def mock_completion(self, ws, messages):
        """Local-dev stand-in for Workers AI (set MOCK_AI=1)."""
        reply = f"*(mock AI)* You said: **{messages[-1]['content']}**"
        for word in reply.split(" "):
            self.send(ws, "token", word + " ")
        return reply

    async def load_history(self):
        raw = await self.ctx.storage.get("messages")
        return json.loads(raw) if isinstance(raw, str) else []

    async def save_message(self, session_id, role, content):
        await self.env.DB.prepare(
            "INSERT INTO messages (id, session_id, role, content) VALUES (?, ?, ?, ?)"
        ).bind(str(uuid.uuid4()), session_id, role, content).run()

    @staticmethod
    def send(ws, msg_type, content):
        ws.send(json.dumps({"type": msg_type, "content": content}))


class StudyPlanWorkflow(WorkflowEntrypoint):
    """Multi-step study-plan job. Steps are implemented in Phase 5."""

    async def run(self, event, step):
        return None


class Default(WorkerEntrypoint):
    async def fetch(self, request):
        url = urlparse(request.url)
        path, method = url.path.rstrip("/") or "/", request.method

        if method == "OPTIONS":
            return Response(None, status=204, headers=self.cors_headers())

        ws_match = SESSION_WS_RE.match(path)
        if ws_match and method == "GET":
            stub = self.env.CHAT_SESSION.get(self.env.CHAT_SESSION.idFromName(ws_match.group(1)))
            return await stub.fetch(request)

        try:
            if path == "/api/sessions" and method == "POST":
                return await self.create_session(request)
            if path == "/api/sessions" and method == "GET":
                user_id = parse_qs(url.query).get("user_id", [""])[0]
                return await self.list_sessions(user_id)
            messages_match = SESSION_MESSAGES_RE.match(path)
            if messages_match and method == "GET":
                return await self.list_messages(messages_match.group(1))
            if path in ("/", "/api/health"):
                return self.json({"status": "ok", "service": "study-buddy-edge"})
        except Exception as e:  # noqa: BLE001
            print(f"api error: {e!r}")
            return self.json({"error": "Internal error"}, status=500)

        return self.json({"error": "Not found"}, status=404)

    async def create_session(self, request):
        try:
            body = json.loads(await request.text() or "{}")
        except ValueError:
            return self.json({"error": "Invalid JSON"}, status=400)
        user_id = str(body.get("user_id") or "").strip()
        if not user_id:
            return self.json({"error": "user_id is required"}, status=400)

        session_id = str(uuid.uuid4())
        await self.env.DB.prepare("INSERT OR IGNORE INTO users (id) VALUES (?)").bind(user_id).run()
        await self.env.DB.prepare(
            "INSERT INTO sessions (id, user_id, title) VALUES (?, ?, 'New Chat')"
        ).bind(session_id, user_id).run()
        return self.json({"id": session_id, "title": "New Chat"}, status=201)

    async def list_sessions(self, user_id):
        if not user_id:
            return self.json({"error": "user_id is required"}, status=400)
        result = await self.env.DB.prepare(
            "SELECT id, title, created_at, updated_at FROM sessions "
            "WHERE user_id = ? ORDER BY updated_at DESC LIMIT 50"
        ).bind(user_id).all()
        return self.json({"sessions": rows(result)})

    async def list_messages(self, session_id):
        result = await self.env.DB.prepare(
            "SELECT id, role, content, created_at FROM messages "
            "WHERE session_id = ? ORDER BY created_at, rowid"
        ).bind(session_id).all()
        return self.json({"messages": rows(result)})

    def cors_headers(self):
        return {
            "Access-Control-Allow-Origin": getattr(self.env, "ALLOWED_ORIGIN", None) or "*",
            "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type",
        }

    def json(self, data, status=200):
        return Response(
            json.dumps(data),
            status=status,
            headers={"Content-Type": "application/json", **self.cors_headers()},
        )
