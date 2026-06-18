"""API authentication — API keys and identity resolution.

Phase 7 replaces the Phase 4 auth placeholder with real API-key
validation.  The ``ApiKeyStore`` persists hashed keys to a JSON file;
``get_auth_context`` (in ``engine.api.dependencies``) reads the
``Authorization: Bearer <key>`` header and resolves the caller identity.
"""

from engine.api.auth.store import ApiKeyEntry, ApiKeyStore, load_api_key_store

__all__ = [
    "ApiKeyEntry",
    "ApiKeyStore",
    "load_api_key_store",
]
