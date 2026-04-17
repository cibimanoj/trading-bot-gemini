"""Stable import path for persistence. Implementation lives in ``repositories.database``."""

from repositories.database import Database, db_instance

__all__ = ["Database", "db_instance"]
