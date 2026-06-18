"""Conductor Engine API package.

Public surface
--------------
``create_api_app`` is the primary entry point for embedding the API in
another application or for programmatic use in tests.

``SSEEventBus`` is exported for callers that need to wire up live event
streaming when building a supervisor outside of ``cond serve``.

``ApiKeyStore`` is exported for programmatic API key management.
"""

from engine.api.app import create_api_app
from engine.api.auth import ApiKeyStore, load_api_key_store
from engine.api.bus import SSEEventBus

__all__ = [
    "ApiKeyStore",
    "SSEEventBus",
    "create_api_app",
    "load_api_key_store",
]
