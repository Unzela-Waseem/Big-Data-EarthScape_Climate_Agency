#!/bin/sh
cd "$(dirname "$0")/.." || exit 1
.venv/bin/python scripts/export_backup.py
