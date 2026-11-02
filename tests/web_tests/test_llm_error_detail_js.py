"""chat.js readableErrorMessage 的纯函数契约（issue #304）。"""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

CHAT_JS = Path(__file__).parents[2] / "web" / "static" / "chat.js"

_HARNESS = """
const fs = require('fs');
const vm = require('vm');
const src = fs.readFileSync(process.argv[1], 'utf8');
const start = src.indexOf('function readableErrorMessage');
if (start < 0) throw new Error('readableErrorMessage not found');
const end = src.indexOf('\\n}\\n', start);
if (end < 0) throw new Error('readableErrorMessage end not found');
const fn = src.slice(start, end + 3);
const context = {};
vm.createContext(context);
vm.runInContext("const ERROR_MESSAGES = {run_in_progress: 'BUSY'};" + fn, context);
const inputs = JSON.parse(process.argv[2]);
const out = inputs.map((item) => context.readableErrorMessage(item));
process.stdout.write(JSON.stringify(out));
"""


@pytest.fixture(scope="module", autouse=True)
def _require_node():
    if shutil.which("node") is None:
        pytest.skip("node unavailable")


def _call(inputs):
    result = subprocess.run(
        ["node", "-e", _HARNESS, str(CHAT_JS), json.dumps(inputs)],
        check=True, capture_output=True, text=True, encoding="utf-8",
    )
    return json.loads(result.stdout)


def test_readable_error_message_appends_detail():
    out = _call([
        {"message": "HTTPStatusError: 400", "detail": "provider body"},
        {"message": "only message"},
        {"code": "run_in_progress"},
    ])
    assert out[0] == "HTTPStatusError: 400\nprovider body"
    assert out[1] == "only message"
    assert out[2] == "BUSY"
