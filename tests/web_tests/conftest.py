# tests/web_tests/conftest.py
"""Fixtures and markers for web UI browser tests."""
import os
from pathlib import Path
import pytest

# Load .env for API key detection (same as cli.py does)
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env")
except ImportError:
    pass


def is_real_api_configured() -> bool:
    """Check if API keys are configured for real API tests."""
    return bool(os.environ.get("OPENAI_API_KEY"))


def pytest_addoption(parser):
    parser.addoption(
        "--run-real-api",
        action="store_true",
        default=False,
        help="Run tests that require a real LLM API (browser E2E)",
    )


def pytest_collection_modifyitems(config, items):
    if not config.getoption("--run-real-api") or not is_real_api_configured():
        skip_real = pytest.mark.skip(reason="--run-real-api not set or no API key configured")
        for item in items:
            if "real_api" in item.keywords:
                item.add_marker(skip_real)
