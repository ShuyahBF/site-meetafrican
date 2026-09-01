"""Unit tests for the deployment-resilience fix (index perms + startup steps)."""
import asyncio
import sys

from pymongo.errors import OperationFailure, ServerSelectionTimeoutError

sys.path.insert(0, "/app/backend")


class _FakeColl:
    name = "maf_users"

    def __init__(self, exc):
        self._exc = exc

    async def create_index(self, keys, **kwargs):
        raise self._exc


def _fake_db(exc):
    return type("D", (), {"__getattr__": lambda self, n: _FakeColl(exc)})()


def test_ensure_indexes_swallows_operation_failure(monkeypatch):
    import db as db_module

    exc = OperationFailure(
        "not authorized on site_meetafrican to execute command createIndexes", 13
    )
    monkeypatch.setattr(db_module, "db", _fake_db(exc))
    asyncio.run(db_module.ensure_indexes())


def test_ensure_indexes_swallows_generic_pymongo_error(monkeypatch):
    import db as db_module

    monkeypatch.setattr(db_module, "db", _fake_db(ServerSelectionTimeoutError("no server")))
    asyncio.run(db_module.ensure_indexes())


def test_on_startup_continues_when_every_step_fails(monkeypatch):
    import server

    calls = []

    async def failing():
        calls.append(1)
        raise OperationFailure("not authorized", 13)

    monkeypatch.setattr(server, "ensure_indexes", failing)
    monkeypatch.setattr(server, "seed_default_plans", failing)
    monkeypatch.setattr(server, "ensure_admin_user", failing)
    asyncio.run(server.on_startup())
    assert len(calls) == 3


def test_ensure_indexes_succeeds_on_real_mongomock():
    import db as db_module

    asyncio.run(db_module.ensure_indexes())
