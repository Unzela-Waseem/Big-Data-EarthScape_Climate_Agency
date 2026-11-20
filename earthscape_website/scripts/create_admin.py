#!/usr/bin/env python3
"""
EarthScape Climate Agency — Admin & Test User Creator
======================================================
Creates default admin and analyst users with hashed passwords.
Reads configuration from .env.

Usage:
    cd earthscape_website
    python scripts/create_admin.py
"""

import os
import sys
from datetime import datetime, timezone

from dotenv import load_dotenv
from pymongo import MongoClient
from werkzeug.security import generate_password_hash

# ── Load environment ──────────────────────────────────────
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))
MONGO_URI = os.getenv('MONGO_URI', 'mongodb://localhost:27017/earthscape')


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


# ── Default Users ─────────────────────────────────────────
DEFAULT_USERS = [
    {
        'username': 'admin',
        'email': 'admin@earthscape.agency',
        'password': 'Admin@123',
        'role': 'admin',
        'full_name': 'System Administrator',
        'is_active': True,
    },
    {
        'username': 'analyst',
        'email': 'analyst@earthscape.agency',
        'password': 'Analyst@123',
        'role': 'analyst',
        'full_name': 'Climate Analyst',
        'is_active': True,
    },
]


def create_users(db):
    """Create or update default users with hashed passwords."""
    users_col = db.users
    now = datetime.now(timezone.utc)

    for user_data in DEFAULT_USERS:
        username = user_data['username']
        existing = users_col.find_one({'username': username})

        doc = {
            'username': user_data['username'],
            'email': user_data['email'],
            'password': generate_password_hash(user_data['password']),
            'password_hash': generate_password_hash(user_data['password']),
            'role': user_data['role'],
            'full_name': user_data['full_name'],
            'active': user_data['is_active'],
            'is_active': user_data['is_active'],
            'updated_at': now,
        }

        if existing:
            users_col.update_one({'username': username}, {'$set': doc})
            print(f"  [↻] Updated existing user: {username} (role={user_data['role']})")
        else:
            doc['created_at'] = now
            users_col.insert_one(doc)
            print(f"  [+] Created new user: {username} (role={user_data['role']})")

    print()


def main():
    db = connect_db()

    print("\n[Creating default users …]\n")
    create_users(db)

    # Summary
    total = db.users.count_documents({})
    print("=" * 50)
    print("  USER CREATION COMPLETE")
    print("=" * 50)
    print(f"  Total users in database: {total}")
    print()
    print("  Default Credentials:")
    print("  ─────────────────────────────────────")
    for u in DEFAULT_USERS:
        print(f"  Username : {u['username']}")
        print(f"  Password : {u['password']}")
        print(f"  Role     : {u['role']}")
        print(f"  Email    : {u['email']}")
        print("  ─────────────────────────────────────")
    print()
    print("  ⚠  Change default passwords in production!")
    print("=" * 50)


if __name__ == '__main__':
    main()
