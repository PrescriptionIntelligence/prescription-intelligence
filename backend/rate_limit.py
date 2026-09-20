"""
Shared rate-limiter instance.

Imported by backend/main.py (which attaches it to app.state)
and by routers that decorate individual endpoints.

Using a module-level singleton means all routers share the same
in-memory counter store.  In a multi-process deployment, point
`storage_uri` at Redis instead.
"""

import os

from slowapi import Limiter
from slowapi.util import get_remote_address

# Allow the storage backend to be overridden via environment variable.
# Default is in-process memory (suitable for a single uvicorn worker).
_storage_uri = os.getenv("RATELIMIT_STORAGE_URL", "memory://")

limiter = Limiter(
    key_func=get_remote_address,
    storage_uri=_storage_uri,
)
