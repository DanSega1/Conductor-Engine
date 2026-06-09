"""Conductor Engine API package.

Public surface
--------------
``create_api_app`` is the primary entry point for embedding the API in
another application or for programmatic use in tests.

``SSEEventBus`` is exported for callers that need to wire up live event
streaming when building a supervisor outside of ``cond serve``.
"""

from engine.api.app import create_api_app
from engine.api.bus import SSEEventBus

__all__ = ["SSEEventBus", "create_api_app"]
