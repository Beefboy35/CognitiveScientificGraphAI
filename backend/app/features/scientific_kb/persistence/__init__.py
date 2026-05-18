"""Persistence layer for the Scientific KB.

Each adapter mirrors the in-memory state into a backing store.  Adapters are
intentionally tolerant: when a store is unreachable they log a warning and
become no-ops so the demo continues to work in fully local mode.
"""

from __future__ import annotations

from .manager import PersistenceManager

__all__ = ["PersistenceManager"]
