"""
EarthScape Climate Agency — MongoDB Connection Helper
Provides a lazy, singleton connection to the *earthscape* database.
"""

import sys
from pymongo import MongoClient, ASCENDING
from pymongo.errors import PyMongoError
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
        print("[db] MONGO_URI is not configured.", file=sys.stderr)
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
    except PyMongoError as exc:
        # Do not include connection details: driver errors may contain host or auth data.
        print(f"[db] MongoDB is unavailable ({type(exc).__name__}).", file=sys.stderr)
        if _client is not None:
            _client.close()
            _client = None
        return None


def _ensure_indexes(db):
    """Create indexes that speed up the most common queries."""
    try:
        # Date and natural-key indexes keep time-series reads and idempotent loads fast.
        db.monthly_climate.create_index([("date", ASCENDING)], background=True)
        db.monthly_climate.create_index(
            [("year", ASCENDING), ("month", ASCENDING)], unique=True, background=True
        )
        db.annual_ghg.create_index([("year", ASCENDING), ("country", ASCENDING)], unique=True, background=True)
        db.arctic_ice.create_index([("month", ASCENDING)], unique=True, background=True)
        db.forecast.create_index([("month", ASCENDING)], unique=True, background=True)
        db.alerts.create_index([("month", ASCENDING)], unique=True, background=True)
        db.alerts.create_index([("level", ASCENDING)], background=True)
        db.users.create_index([("username", ASCENDING)], unique=True, background=True)
        db.feedback.create_index([("user_id", ASCENDING), ("created_at", ASCENDING)], background=True)
        db.audit.create_index([("timestamp", ASCENDING)], background=True)
        db.live_weather.create_index(
            [("city", ASCENDING), ("observed_at", ASCENDING)], unique=True, background=True
        )
    except Exception as exc:  # noqa: BLE001
        print(f"[db] Index creation warning: {exc}", file=sys.stderr)


def close_db():
    """Cleanly close the MongoDB client (call on app teardown)."""
    global _client, _db
    if _client is not None:
        _client.close()
        _client = None
        _db = None
