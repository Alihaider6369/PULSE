"""Vercel Serverless Function entry point for PULSE FastAPI backend."""
import os
import sys
from pathlib import Path

# Add project root and backend directory to Python path
ROOT_DIR = Path(__file__).resolve().parent.parent
BACKEND_DIR = ROOT_DIR / "backend"

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

# Ensure VERCEL environment flag is detected
os.environ.setdefault("VERCEL", "1")

from app.main import app
