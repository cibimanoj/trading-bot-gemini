"""Ensure thin ``db.database`` shim points at the same singleton as ``repositories.database``."""

from db.database import db_instance as from_db
from repositories.database import db_instance as from_repo


def test_db_instance_is_single_singleton():
    assert from_db is from_repo
