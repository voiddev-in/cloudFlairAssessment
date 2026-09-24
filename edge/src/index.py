from js import Response, WebSocketPair, JSON
from pyodide.ffi import to_js
import json
import uuid

class ChatSession:
    def __init__(self, ctx, env):
        self.ctx = ctx
        self.env = env
        # DO storage for recent messages
        self.storage = ctx.storage

    async def fetch(self, request):
        upgrade_header = request.headers.get("Upgrade")
        if upgrade_header != "websocket":
            return Response.new("Expected Upgrade: websocket", status=426)

        pair = WebSocketPair.new()
        client = pair[0]
        server = pair[1]

        # Extract session_id from URL
        # e.g. /api/sessions/{session_id}/ws
        url = request.url
        parts = url.split("/")
        self.session_id = parts[-2]

        server.accept()

        async def on_message(event):
            try:
                data = json.loads(event.data)
                msg_type = data.get("type")
                if msg_type == "user_msg":
                    content = data.get("content")
                    # 1. Save to D1 (background)
                    msg_id = str(uuid.uuid4())
                    self.ctx.waitUntil(
                        self.env.DB.prepare(
                            "INSERT INTO messages (id, session_id, role, content) VALUES (?, ?, 'user', ?)"
                        ).bind(msg_id, self.session_id, content).run()
                    )
                    
                    # 2. Get recent messages from DO storage (short term memory)
                    recent = await self.storage.get("messages")
                    if not recent:
                        recent = []
                    recent.append({"role": "user", "content": content})
                    
                    # 3. Call Llama
                    messages = [{"role": "system", "content": "You are a helpful study buddy assistant."}] + recent
                    
                    # For simplicity, we use blocking AI call first, streaming can be added if needed
                    # Or we implement a basic stream parser
                    response = await self.env.AI.run(
                        "@cf/meta/llama-3.3-70b-instruct-fp8-fast",
                        to_js({"messages": messages})
                    )
                    
                    reply = response.response
                    recent.append({"role": "assistant", "content": reply})
                    
                    # keep only last 10
                    recent = recent[-10:]
                    await self.storage.put("messages", recent)
                    
                    # Save assistant msg to D1
                    ast_id = str(uuid.uuid4())
                    self.ctx.waitUntil(
                        self.env.DB.prepare(
                            "INSERT INTO messages (id, session_id, role, content) VALUES (?, ?, 'assistant', ?)"
                        ).bind(ast_id, self.session_id, reply).run()
                    )
                    
                    # Send response back
                    server.send(json.dumps({"type": "done", "content": reply}))
            except Exception as e:
                server.send(json.dumps({"type": "error", "content": str(e)}))

        # Pyodide needs to bind event listeners
        # Using a proxy or direct JS assignment might be needed
        # In cloudflare python workers, you can just do:
        server.addEventListener("message", on_message)
        
        # return client websocket
        # passing webSocket as kwarg might not work, let's build the response dict
        # wait, Response.new in python cloudflare doesn't easily accept kwargs for webSocket
        # let's try kwargs first, if it fails, we fall back.
        # Another way: `new Response(null, {status: 101, webSocket: client})`
        # in pyodide: `js.Response.new(None, to_js({"status": 101, "webSocket": client}, dict_converter=js.Object.fromEntries))`
        from js import Object
        opts = Object.new()
        opts.status = 101
        opts.webSocket = client
        return Response.new(None, opts)

class Default:
    def __init__(self, ctx, env):
        self.env = env
        self.ctx = ctx

    async def fetch(self, request):
        url = request.url
        method = request.method
        
        # CORS headers
        headers = {
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type",
        }
        
        if method == "OPTIONS":
            return Response.new("", headers=headers)
            
        if method == "POST" and "api/sessions" in url:
            # Create a session
            session_id = str(uuid.uuid4())
            await self.env.DB.prepare(
                "INSERT INTO sessions (id, title) VALUES (?, ?)"
            ).bind(session_id, "New Chat").run()
            
            return Response.new(
                json.dumps({"id": session_id}), 
                headers={"Content-Type": "application/json", **headers}
            )
            
        if "api/sessions" in url and url.endswith("/ws"):
            # Hand off to DO
            parts = url.split("/")
            session_id = parts[-2]
            
            # Get DO stub
            id = self.env.CHAT_SESSION.idFromName(session_id)
            stub = self.env.CHAT_SESSION.get(id)
            
            # Forward the request to DO
            return await stub.fetch(request)

        # Basic health check
        return Response.new("Study Buddy Edge API", headers=headers)
