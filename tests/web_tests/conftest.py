# tests/web_tests/conftest.py
"""Fixtures and markers for web UI browser tests."""
import os
import pytest

# Load .env for API key detection (same as agent/main.py does)
try:
    from dotenv import load_dotenv
    load_dotenv()
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


@pytest.fixture(autouse=True)
def _isolate_workspace(tmp_path, monkeypatch):
    """隔离 web 测试的工作目录。

    SessionManager 的持久化目录默认为 workspace_root 或 cwd（`<root>/.asterwynd/sessions`），
    uploads 也写入 cwd 下的 `.asterwynd`。autouse 切到 pytest 临时目录，避免测试
    在仓库根累积 `.asterwynd/sessions` 和上传文件。
    """
    monkeypatch.chdir(tmp_path)
    yield tmp_path

