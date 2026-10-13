"""Automated verification suite for PULSE Cloud Deployment, Vercel entrypoint,
and Desktop Synchronization protocol handling.
"""
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "backend"
FRONTEND_DIR = ROOT / "frontend"

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(BACKEND_DIR))


def test_vercel_serverless_entrypoint():
    """Verify api/index.py properly configures sys.path and exports the FastAPI app."""
    import importlib.util

    entrypoint_path = ROOT / "api" / "index.py"
    assert entrypoint_path.exists(), "api/index.py entry point must exist"

    spec = importlib.util.spec_from_file_location("vercel_api_index", entrypoint_path)
    assert spec is not None
    mod = importlib.util.module_from_spec(spec)
    assert mod is not None
    spec.loader.exec_module(mod)

    assert hasattr(mod, "app"), "api/index.py must export 'app' for Vercel Python runtime"
    from fastapi import FastAPI
    assert isinstance(mod.app, FastAPI)
    assert os.environ.get("VERCEL") == "1"


def test_serverless_environment_detection():
    """Verify is_serverless_env detects Vercel and AWS Lambda environment variables."""
    from app.database.session import is_serverless_env

    # Empty env: not serverless
    with patch.dict(os.environ, {"VERCEL": "", "AWS_LAMBDA_FUNCTION_NAME": ""}, clear=False):
        assert is_serverless_env() is False

    # VERCEL=1: serverless
    with patch.dict(os.environ, {"VERCEL": "1", "AWS_LAMBDA_FUNCTION_NAME": ""}, clear=False):
        assert is_serverless_env() is True

    # AWS Lambda: serverless
    with patch.dict(os.environ, {"VERCEL": "", "AWS_LAMBDA_FUNCTION_NAME": "my-lambda"}, clear=False):
        assert is_serverless_env() is True


def test_desktop_protocol_cli_launcher():
    """Verify desktop should_auto_start_monitoring handles 'pulse://start' or '--start'."""
    from desktop_app.main import should_auto_start_monitoring

    # Protocol link
    assert should_auto_start_monitoring(["pulse://start"]) is True
    assert should_auto_start_monitoring(["pulse://start/"]) is True
    assert should_auto_start_monitoring(["PULSE://START"]) is True

    # CLI flag
    assert should_auto_start_monitoring(["--start"]) is True

    # Other flags or empty arguments
    assert should_auto_start_monitoring([]) is False
    assert should_auto_start_monitoring(["--check-integrity"]) is False
    assert should_auto_start_monitoring(["other_arg"]) is False


def test_frontend_launch_and_download_elements():
    """Verify index.html and live.html expose pulse://start launcher and app download links."""
    index_html = (FRONTEND_DIR / "index.html").read_text(encoding="utf-8")
    live_html = (FRONTEND_DIR / "live.html").read_text(encoding="utf-8")

    # index.html check
    assert 'href="pulse://start"' in index_html, "Dashboard index.html must feature pulse://start link"
    assert 'id="btn-download-app"' in index_html, "Dashboard index.html must feature download app link"
    assert "desktop-launch-bar" in index_html

    # live.html check
    assert 'href="pulse://start"' in live_html, "live.html must feature pulse://start link"
    assert 'id="btn-live-download"' in live_html, "live.html must feature download app link"


def test_vercel_json_configuration():
    """Verify vercel.json contains required routes, rewrites, and security headers."""
    import json
    vercel_path = ROOT / "vercel.json"
    assert vercel_path.exists(), "vercel.json must exist"

    with open(vercel_path, "r", encoding="utf-8") as f:
        vcfg = json.load(f)

    # Verify api rewrite
    rewrites = vcfg.get("rewrites", [])
    has_api_rewrite = any("/api" in r.get("source", "") and r.get("destination", "").endswith("api/index.py") for r in rewrites)
    assert has_api_rewrite, "vercel.json must route /api/(.*) to /api/index.py"

    # Verify security headers
    headers = vcfg.get("headers", [])
    assert len(headers) > 0, "vercel.json should specify standard security headers"
