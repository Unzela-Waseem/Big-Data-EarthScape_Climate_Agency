"""
EarthScape Climate Agency — Application Configuration
Loads settings from environment variables via python-dotenv.
"""

import os
from dotenv import load_dotenv

# Load .env from project root
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))


class Config:
    """Central configuration read exclusively from environment variables."""

    MONGO_URI = os.environ.get("MONGO_URI", "")
    SECRET_KEY = os.environ.get("SECRET_KEY", "fallback-dev-key-change-me")
    ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
    ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "Admin@12345")

    # Pagination
    PAGE_SIZE = 50

    # Default alert threshold (°C anomaly)
    DEFAULT_THRESHOLD = 1.50
