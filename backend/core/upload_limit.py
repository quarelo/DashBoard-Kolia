from starlette.responses import JSONResponse


class ImportBodyLimitMiddleware:
    """Bound the complete upload before the multipart parser allocates temp files."""

    def __init__(self, app, max_bytes: int):
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] != "POST" or scope["path"].rstrip("/") != "/api/imports":
            return await self.app(scope, receive, send)
        oversized = JSONResponse({"detail": "Limite de upload: 5 MiB por arquivo."}, status_code=413)
        lengths = [value for key, value in scope.get("headers", []) if key.lower() == b"content-length"]
        try:
            if any(int(length) > self.max_bytes for length in lengths):
                return await oversized(scope, receive, send)
        except ValueError:
            return await JSONResponse({"detail": "Content-Length inválido."}, status_code=400)(scope, receive, send)
        body = bytearray()
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            chunk = message.get("body", b"")
            if len(body) + len(chunk) > self.max_bytes:
                return await oversized(scope, receive, send)
            body.extend(chunk)
            if not message.get("more_body", False):
                break
        sent = False

        async def bounded_receive():
            nonlocal sent
            if sent:
                return await receive()
            sent = True
            return {"type": "http.request", "body": bytes(body), "more_body": False}

        await self.app(scope, bounded_receive, send)
