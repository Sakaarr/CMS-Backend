import time
import uuid
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp


class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response
    

class TimingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start = time.perf_counter()
        response = await call_next(request)
        duration_ms = round((time.perf_counter() - start) * 1000, 2)
        response.headers["X-Process-Time-Ms"] = str(duration_ms)
        return response
    
class TenantMiddleware(BaseHTTPMiddleware):
    """
    Resolves tenant from subdomain or X-Tenant-Slug header.
    Sets request.state.tenant_slug for downstream use.
    Actual tenant DB lookup happens in the dependency layer.
    """

    async def dispatch(self, request: Request, call_next):
        # Try header first (mobile / API clients)
        tenant_slug = request.headers.get("X-Tenant-Slug")

         # Fall back to subdomain (web clients: acme.app.com)
        if not tenant_slug:
            host = request.headers.get("host", "")
            parts = host.split(".")
            if len(parts) >= 3:
                tenant_slug = parts[0]

        request.state.tenant_slug = tenant_slug
        response = await call_next(request)
        return response
