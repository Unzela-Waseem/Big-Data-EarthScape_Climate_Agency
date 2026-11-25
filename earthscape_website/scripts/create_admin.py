#!/usr/bin/env python3
"""Create the first Admin using ADMIN_USERNAME / ADMIN_PASSWORD from .env."""
import os
from datetime import datetime, timezone

from dotenv import load_dotenv
from pymongo import MongoClient
from werkzeug.security import generate_password_hash

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(ROOT, ".env"))


def main():
    uri = os.environ.get("MONGO_URI")
    username = os.environ.get("ADMIN_USERNAME")
    password = os.environ.get("ADMIN_PASSWORD")
    if not all((uri, username, password)):
        raise SystemExit("Set MONGO_URI, ADMIN_USERNAME and ADMIN_PASSWORD in .env first.")
    client = MongoClient(uri, serverSelectionTimeoutMS=8000)
    try:
        client.admin.command("ping")
        users = client["earthscape"].users
        users.create_index("username", unique=True)
        candidates = [
            (username, password, "admin", os.environ.get("ADMIN_FULL_NAME", "System Administrator"), os.environ.get("ADMIN_EMAIL", "")),
            (os.environ.get("ANALYST_USERNAME"), os.environ.get("ANALYST_PASSWORD"), "analyst", "Climate Analyst", ""),
        ]
        for login, secret, role, full_name, email in candidates:
            if role == "admin" and users.count_documents({"role": "admin", "is_active": True}):
                print("An active Admin already exists; no Admin account was changed.")
                continue
            if not login and not secret:
                continue
            if not login or not secret or len(secret) < 12:
                raise SystemExit(f"Configure a username and a 12-character password for the {role} account.")
            if users.find_one({"username": login}):
                print(f"{role.title()} account '{login}' already exists; it was left unchanged.")
                continue
            users.insert_one({"username": login, "password_hash": generate_password_hash(secret),
                              "role": role, "full_name": full_name, "email": email,
                              "is_active": True, "created_at": datetime.now(timezone.utc)})
            print(f"{role.title()} account '{login}' created; change the password after first login.")
    finally:
        client.close()


if __name__ == "__main__":
    main()
