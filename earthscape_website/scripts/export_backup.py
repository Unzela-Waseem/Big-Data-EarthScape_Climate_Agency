#!/usr/bin/env python3
"""Export every MongoDB collection as Extended JSON for local backup."""
import json
import os
from datetime import datetime, timezone

from bson import json_util
from dotenv import load_dotenv
from pymongo import MongoClient

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(ROOT, ".env"))
BACKUP_ROOT = os.path.join(ROOT, "backups")


def main():
    uri = os.environ.get("MONGO_URI")
    if not uri:
        raise SystemExit("Set MONGO_URI in .env before exporting a backup.")
    client = MongoClient(uri, serverSelectionTimeoutMS=8000)
    try:
        client.admin.command("ping")
        db = client["earthscape"]
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        folder = os.path.join(BACKUP_ROOT, f"backup_{stamp}")
        os.makedirs(folder, exist_ok=True)
        count = 0
        collections = sorted(db.list_collection_names())
        for name in collections:
            docs = list(db[name].find({}))
            with open(os.path.join(folder, f"{name}.json"), "w", encoding="utf-8") as stream:
                stream.write(json_util.dumps(docs, indent=2, ensure_ascii=False))
            count += len(docs)
            print(f"Exported {len(docs)} documents from {name}.")
        metadata = {"created_at": datetime.now(timezone.utc).isoformat(),
                    "database": "earthscape", "collections": len(collections),
                    "documents": count}
        with open(os.path.join(folder, "_backup_meta.json"), "w", encoding="utf-8") as stream:
            json.dump(metadata, stream, indent=2)
        print(f"Backup complete: {os.path.abspath(folder)} ({count} documents)")
    finally:
        client.close()


if __name__ == "__main__":
    main()
