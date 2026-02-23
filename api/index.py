"""
api/index.py — Vercel serverless entry point for the FastAPI backend.
Vercel's Python runtime discovers this file and serves the ASGI app.
"""

import sys
import os

# Add the backend directory to Python's module search path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from main import app  # noqa: F401  — re-exported for Vercel
