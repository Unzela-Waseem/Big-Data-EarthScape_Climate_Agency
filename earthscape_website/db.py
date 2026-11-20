"""
EarthScape Climate Agency — MongoDB Connection Helper
Provides a lazy, singleton connection to the *earthscape* database.
"""

import sys
from pymongo import MongoClient, ASCENDING
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError
from config import Config

# ---------------------------------------------------------------------------
# Module-level singletons (populated on first call to get_db)
# ---------------------------------------------------------------------------
_client = None
_db = None


def get_db():
    """
    Return the *earthscape* database handle.

    On first call the connection is established and indexes are created.
    If the connection fails, an error is printed (no raw traceback) and
    ``None`` is returned so that callers can degrade gracefully.
    """
    global _client, _db

    if _db is not None:
        return _db

    uri = Config.MONGO_URI
    if not uri:
        print("[db] MONGO_URI is empty — set it in .env", file=sys.stderr)
        return None

    try:
        _client = MongoClient(
            uri,
            serverSelectionTimeoutMS=5000,
            connectTimeoutMS=5000,
            socketTimeoutMS=10000,
        )
        # Force a round-trip to verify the connection
        _client.admin.command("ping")
        _db = _client["earthscape"]
        _ensure_indexes(_db)
        print("[db] Connected to MongoDB Atlas — earthscape database ready.")
        return _db
    except Exception as exc:
        print(f"[db] Atlas connection/auth failed ({exc}). Trying local MongoDB fallback...", file=sys.stderr)
        try:
            _client = MongoClient("mongodb://localhost:27017", serverSelectionTimeoutMS=3000)
            _client.admin.command("ping")
            _db = _client["earthscape"]
            _ensure_indexes(_db)
            print("[db] Connected to Local MongoDB fallback — earthscape database ready.")
            return _db
        except Exception as local_exc:
            print(f"[db] All MongoDB connections failed: {local_exc}", file=sys.stderr)
            return None


def _ensure_indexes(db):
    """Create indexes that speed up the most common queries."""
    try:
        # monthly_climate — sort / filter by year+month
        db.monthly_climate.create_index(
            [("year", ASCENDING), ("month", ASCENDING)], background=True
        )
        # forecast — sort by horizon / date
        db.forecast.create_index([("horizon", ASCENDING)], background=True)
        db.forecast.create_index(
            [("year", ASCENDING), ("month", ASCENDING)], background=True
        )
        # alerts — sort by date, filter by level
        db.alerts.create_index(
            [("year", ASCENDING), ("month", ASCENDING)], background=True
        )
        db.alerts.create_index([("level", ASCENDING)], background=True)
    except Exception as exc:  # noqa: BLE001
        print(f"[db] Index creation warning: {exc}", file=sys.stderr)


def close_db():
    """Cleanly close the MongoDB client (call on app teardown)."""
    global _client, _db
    if _client is not None:
        _client.close()
        _client = None
        _db = None
