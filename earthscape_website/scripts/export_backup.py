#!/usr/bin/env python3
"""
EarthScape Climate Agency — Export Backup
==========================================
Exports all MongoDB collections to timestamped JSON backup files.

Usage:
    cd earthscape_website
    python scripts/export_backup.py
"""

import os
import sys
import json
from datetime import datetime, timezone

from dotenv import load_dotenv
from pymongo import MongoClient
from bson import ObjectId, json_util

# ── Load environment ──────────────────────────────────────
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))
MONGO_URI = os.getenv('MONGO_URI', 'mongodb://localhost:27017/earthscape')

# ── Backup directory ──────────────────────────────────────
BACKUP_ROOT = os.path.join(os.path.dirname(__file__), '..', 'backups')


class MongoEncoder(json.JSONEncoder):
    """Custom encoder for MongoDB-specific types."""
    def default(self, obj):
        if isinstance(obj, ObjectId):
            return str(obj)
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)


def connect_db():
    uri = os.getenv('MONGO_URI')
    if uri:
        try:
            client = MongoClient(uri, serverSelectionTimeoutMS=4000)
            client.admin.command('ping')
            db = client['earthscape']
            print(f"[✓] Connected to MongoDB Atlas: earthscape")
            return db
        except Exception as e:
            print(f"[!] Atlas connection failed: {e}")
            print("[*] Falling back to local MongoDB...")

    client = MongoClient('mongodb://localhost:27017', serverSelectionTimeoutMS=3000)
    db = client['earthscape']
    print(f"[✓] Connected to Local MongoDB: earthscape")
    return db


def export_collection(db, col_name, backup_dir):
    """Export a single collection to a JSON file."""
    collection = db[col_name]
    docs = list(collection.find())
    count = len(docs)

    if count == 0:
        print(f"  [—] {col_name}: empty, skipped")
        return 0

    filepath = os.path.join(backup_dir, f"{col_name}.json")
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(docs, f, cls=MongoEncoder, indent=2, ensure_ascii=False)

    size_kb = os.path.getsize(filepath) / 1024
    print(f"  [✓] {col_name}: {count} docs → {filepath} ({size_kb:.1f} KB)")
    return count


def main():
    db = connect_db()

    # Create timestamped backup directory
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_dir = os.path.join(BACKUP_ROOT, f"backup_{timestamp}")
    os.makedirs(backup_dir, exist_ok=True)
    print(f"\n[Backup directory: {os.path.abspath(backup_dir)}]\n")

    # Get all collection names
    collections = db.list_collection_names()
    if not collections:
        print("  No collections found in database!")
        return

    print(f"Found {len(collections)} collection(s): {', '.join(collections)}\n")

    total_docs = 0
    total_files = 0

    for col_name in sorted(collections):
        count = export_collection(db, col_name, backup_dir)
        if count > 0:
            total_docs += count
            total_files += 1

    # Write a metadata file
    meta = {
        'timestamp': timestamp,
        'mongo_uri': MONGO_URI.split('@')[-1] if '@' in MONGO_URI else MONGO_URI,
        'collections_exported': total_files,
        'total_documents': total_docs,
        'created_at': datetime.now(timezone.utc).isoformat(),
    }
    meta_path = os.path.join(backup_dir, '_backup_meta.json')
    with open(meta_path, 'w', encoding='utf-8') as f:
        json.dump(meta, f, indent=2)

    print()
    print("=" * 50)
    print("  BACKUP COMPLETE")
    print("=" * 50)
    print(f"  Directory  : {os.path.abspath(backup_dir)}")
    print(f"  Collections: {total_files}")
    print(f"  Documents  : {total_docs}")
    print(f"  Metadata   : {meta_path}")
    print("=" * 50)


if __name__ == '__main__':
    main()
