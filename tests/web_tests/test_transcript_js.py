# tests/web_tests/test_transcript_js.py
"""前端纯函数：harness 式工具执行行摘要（change ``harness-style-web-transcript``）。

覆盖 D3（折叠行摘要生成）、D4（失败态识别）、D6（无调用时的结果摘要）三条决策的
可机械断言部分。这些函数是 ``tool_rows.js`` 里 DOM 无关的一层，用 node + ``vm``
直接跑（沿用 ``test_workflow_graph_js.py`` 的 harness 写法）。

为什么不在浏览器里断言这些：摘要生成是**字符串**语义（截断长度、字段优先级、
失败特征识别），源码字符串断言测不到，Playwright 断言只能看到最终渲染结果，
失败定位成本高。纯函数层单独锁死，浏览器只锁「折叠/展开行为」。

失败特征集必须对齐后端**自己的** canonical 错误通道（``agent/loop.py`` 的
``_text_prefix_guess`` + registry/approval 的拒绝文案）——对齐不上，最常见的失败
（审批被拒、权限拒绝、工具抛错）会全部显示成成功（grill R-A）。
"""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

TRANSCRIPT_JS = Path(__file__).parents[2] / "web" / "static" / "tool_rows.js"

_HARNESS = """
const fs = require('fs');
const vm = require('vm');
const source = fs.readFileSync(process.argv[1], 'utf8');
const calls = JSON.parse(process.argv[2]);
const context = { window: {} };
vm.createContext(context);
vm.runInContext(source, context);
const api = context.window.AsterwyndToolRows;
const out = calls.map(([name, argv]) => api[name](...argv));
process.stdout.write(JSON.stringify(out));
"""


@pytest.fixture(scope="module", autouse=True)
def _require_node():
    if shutil.which("node") is None:
        pytest.skip("node unavailable")


def call(*calls):
    """按顺序调用 ``AsterwyndToolRows`` 上的函数，返回结果列表。"""
    result = subprocess.run(
        ["node", "-e", _HARNESS, str(TRANSCRIPT_JS), json.dumps(list(calls))],
        check=True, capture_output=True, text=True, encoding="utf-8",
    )
    return json.loads(result.stdout)


def one(name, *args):
    return call([name, list(args)])[0]


# --- 基础文本工具 -----------------------------------------------------------


def test_first_line_cuts_at_newline():
    assert one("firstLine", "line one\nline two\nline three") == "line one"


def test_first_line_handles_single_line_and_empty():
    assert one("firstLine", "only") == "only"
    assert one("firstLine", "") == ""
    assert one("firstLine", "\n\nsecond") == ""


def test_first_line_tolerates_non_string():
    # 事件字段可能缺失或不是字符串；摘要层 SHALL NOT 抛异常。
    assert one("firstLine", None) == ""
    assert one("firstLine", 42) == "42"


def test_truncate_marks_elision_and_respects_limit():
    text = "x" * 200
    out = one("truncate", text, 20)
    assert len(out) == 20
    assert out.endswith("…")
    assert out.startswith("x" * 19)


def test_truncate_leaves_short_text_untouched():
    assert one("truncate", "short", 20) == "short"


def test_truncate_collapses_whitespace_runs():
    assert one("truncate", "a   b\n\tc", 80) == "a b c"


def test_compact_json_serializes_objects():
    out = one("compactJson", {"b": 1, "a": [1, 2]}, 200)
    assert out == '{"b":1,"a":[1,2]}'


def test_compact_json_passes_strings_through():
    assert one("compactJson", "plain text", 200) == "plain text"


def test_compact_json_handles_non_object_values():
    # 摘要层不得因为字段缺失/类型意外而炸掉整条渲染路径（前端一次未捕获异常会让
    # 后续所有事件都渲染不出来），必须一律降级成字符串。
    for value in (None, 0, False, [], {}):
        assert isinstance(one("compactJson", value, 200), str)


def test_compact_json_truncates():
    out = one("compactJson", {"key": "v" * 500}, 30)
    assert len(out) == 30
    assert out.endswith("…")


# --- 工具标题 ---------------------------------------------------------------


def test_tool_title_maps_known_tools_to_verbs():
    titles = one("toolTitle", "Read"), one("toolTitle", "Bash"), one("toolTitle", "Grep")
    assert titles == ("Read", "Bash", "Grep")


def test_tool_title_maps_webfetch_to_short_verb():
    # 与 DSH 的 `tool.title.webFetch` = "Fetch" 同口径：行宽有限，标题要短。
    assert one("toolTitle", "WebFetch") == "Fetch"


def test_tool_title_falls_back_to_wire_name_for_unknown_tool():
    # 未知工具（MCP / 插件工具）标题回落线名本身，绝不能变成空标题。
    assert one("toolTitle", "mcp__foo__bar") == "mcp__foo__bar"
    assert one("toolTitle", "") == "工具"


# --- 工具调用摘要 -----------------------------------------------------------


def test_summarize_read_prefers_path():
    assert one("summarizeToolCall", "Read", {"path": "agent/loop.py"}) == "agent/loop.py"


def test_summarize_bash_prefers_cmd():
    assert one("summarizeToolCall", "Bash", {"cmd": "uv run pytest -q"}) == "uv run pytest -q"


def test_summarize_bash_uses_first_line_only():
    out = one("summarizeToolCall", "Bash", {"cmd": "cd /tmp\nrm -rf x"})
    assert out == "cd /tmp"


def test_summarize_grep_combines_pattern_and_path():
    # 搜索类光看 pattern 定位不到「搜哪儿」，两个字段都要进摘要。
    out = one("summarizeToolCall", "Grep", {"pattern": "def main", "path": "agent/"})
    assert "def main" in out
    assert "agent/" in out


def test_summarize_webfetch_uses_url():
    out = one("summarizeToolCall", "WebFetch", {"url": "https://example.com/doc"})
    assert out == "https://example.com/doc"


def test_summarize_unknown_tool_prefers_first_string_value():
    # 参考实现的 generic 行口径：最后一个回落是「参数对象里第一个非空字符串值」
    # （`deriveSummary` 第 4 步），比直接糊 JSON 可读。
    assert one("summarizeToolCall", "MysteryTool", {"alpha": "beta"}) == "beta"


def test_summarize_unknown_tool_falls_back_to_json_when_no_string_values():
    # 没有可用字符串时才糊压缩 JSON——此时 JSON 是唯一能表达「传了什么」的形态。
    out = one("summarizeToolCall", "MysteryTool", {"count": 3, "flag": True})
    assert "count" in out and "3" in out


def test_summarize_tolerates_missing_args():
    # `tool_call` 事件在参数解析失败路径上带 `{}`；不得抛异常、不得产出 "undefined"。
    for args in (None, {}, "", "not-json{{{"):
        out = one("summarizeToolCall", "Read", args)
        assert isinstance(out, str)
        assert "undefined" not in out


def test_summarize_accepts_string_arguments():
    assert one("summarizeToolCall", "Read", '{"path": "README.md"}') == "README.md"
    assert one("summarizeToolCall", "Read", "raw text") == "raw text"


def test_summarize_truncates_long_values():
    out = one("summarizeToolCall", "Bash", {"cmd": "echo " + "y" * 400})
    assert len(out) <= 80
    assert out.endswith("…")


def test_summarize_todowrite_reports_operation():
    assert one("summarizeToolCall", "TodoWrite", {"operation": "create", "content": "跑测试"}) == "跑测试"
    updated = one("summarizeToolCall", "TodoWrite", {"operation": "update", "id": "3", "status": "completed"})
    assert "3" in updated and "completed" in updated


def test_summarize_never_returns_empty_for_known_tool_with_args():
    assert one("summarizeToolCall", "Write", {"path": "a/b.py", "content": "x"}) == "a/b.py"


# --- 工具结果摘要与失败识别 -------------------------------------------------


def test_result_ok_has_no_error_state():
    out = one("summarizeToolResult", "Bash", "all good\nsecond line")
    assert out["state"] == "ok"


def test_result_detects_error_prefix():
    out = one("summarizeToolResult", "Bash", "Error: no such file or directory")
    assert out["state"] == "error"
    assert out["summary"].startswith("Error:")


def test_result_detects_traceback():
    out = one("summarizeToolResult", "Bash", "Traceback (most recent call last):\n  File x")
    assert out["state"] == "error"


def test_result_detects_backend_canonical_error_prefixes():
    """后端 canonical 错误通道的前缀必须全部认出（grill R-A / Q1）。

    这些前缀由 ``agent/loop.py::_text_prefix_guess`` 与 registry/approval 的拒绝文案
    产生，是**最常见的失败**（参数解析失败、未知工具、权限拒绝、审批被拒、MCP 错误）。
    漏掉任何一个，「失败在折叠行上可见」这条验收就在主路径上不成立。
    """
    cases = [
        "[Error: file missing: /tmp/x]",
        "[Permission denied: tool Read is not allowed in plan mode: nope]",
        "[Approval denied: tool Bash was not approved in build mode: no]",
        "[Approval unavailable: tool Bash requires approval in build mode: timeout]",
        "[Approval required: tool Bash requires approval in build mode]",
        "[MCP tool error: server gone]",
    ]
    for text in cases:
        out = one("summarizeToolResult", "Bash", text)
        assert out["state"] == "error", text
        assert out["summary"], text


def test_result_ignores_failure_words_inside_a_line():
    """未锚定的失败模式必须收敛掉：Grep 命中的源码行可能**包含**失败字样。

    本仓库里就真实存在这样一行（``tests/web_tests/test_transcript_js.py`` 的用例数据
    ``"command failed with exit status 128"``）。把它判成失败，会让完全成功的搜索
    整片标红——比不标还糟。
    """
    for text in (
        "agent/x.py:3: msg = failed with exit code 3",
        "tests/t.py:221: for text in (\"exit code 1\", \"command failed with exit status 128\"):",
        "0 errors, 12 passed",
        "[Exit 0] all good",
    ):
        assert one("summarizeToolResult", "Grep", text)["state"] == "ok", text


def test_result_reports_structured_bash_failure():
    """Bash 的真实线上形态：``SandboxResult.to_json()`` 单行 JSON（grill Q2）。

    ``[Exit N] …`` 是 ``SandboxResult.__str__`` 的格式，chat 的 WS 路径上并不产生；
    真正到达前端的是这种 JSON 信封。判失败之外还要给出短因由（``exit 1``），
    调用方才能在保留命令摘要的同时把失败信号放行尾。
    """
    payload = (
        '{"exit_code": 1, "stdout": "1 failed, 12 passed", "stderr": "", '
        '"duration_ms": 7345.2, "timed_out": false, "oom_killed": false, "degraded": false}'
    )
    out = one("summarizeToolResult", "Bash", payload)
    assert out["state"] == "error"
    assert out["structured"] is True
    assert out["code"] == "exit 1"
    # 结构化失败**不**给可读摘要：调用方要保留参数摘要（命令才是定位符）。
    assert out["summary"] == ""


def test_result_accepts_zero_exit_structured_payload():
    payload = '{"exit_code": 0, "stdout": "ok", "stderr": "", "duration_ms": 1.0, "timed_out": false}'
    out = one("summarizeToolResult", "Bash", payload)
    assert out["state"] == "ok"
    assert out["code"] == ""


def test_result_detects_failed_background_task():
    """``TaskOutput`` 的结果**不是** JSON 信封，是多行 ``key: value``。

    真实形态见 ``agent/loop.py::_format_task_output``：首行 ``[Task <id>]``，随后
    ``status: …`` / ``exit_code: …`` / ``stdout: …``。漏掉它，「后台命令失败了」在折叠行
    上会显示成成功（review MEDIUM-1）。
    """
    failed = one("summarizeToolResult", "TaskOutput",
                 "[Task t1]\nstatus: failed\nexit_code: 1\nstdout: boom")
    assert failed["state"] == "error"
    assert failed["code"] == "failed"
    assert failed["structured"] is True
    assert failed["summary"] == ""

    timed_out = one("summarizeToolResult", "TaskOutput",
                    "[Task t2]\nstatus: timeout\nexit_code: None\nstdout: partial")
    assert timed_out["state"] == "error"
    assert timed_out["code"] == "timeout"


def test_result_detects_completed_task_with_nonzero_exit_code():
    out = one("summarizeToolResult", "TaskOutput",
              "[Task t3]\nstatus: completed\nexit_code: 2\nstdout: nope")
    assert out["state"] == "error"
    assert out["code"] == "exit 2"


def test_result_accepts_running_and_successful_tasks():
    for text in (
        "[Task t4]\nstatus: running\nexit_code: None\nstdout: ",
        "[Task t5]\nstatus: completed\nexit_code: 0\nstdout: ok",
        "[Task t6]\nstatus: completed\nexit_code: None\nstdout: ok",
    ):
        assert one("summarizeToolResult", "TaskOutput", text)["state"] == "ok", text


def test_task_failure_requires_the_task_header_as_a_gate():
    """`status: failed` 出现在普通文件内容里不得被判成失败。

    门是首行的 ``[Task …]``——没有它，读一个恰好含该键值行的 YAML/配置文件就会被标红。
    """
    for text in (
        "name: ci\nstatus: failed\nexit_code: 1\n",
        "some/file.yml:3: status: failed",
        "[Task-ish]\nstatus: failed",
    ):
        assert one("summarizeToolResult", "TaskOutput", text)["state"] == "ok", text


def test_task_scan_stops_at_the_stdout_body():
    """``stdout:`` 之后是命令输出正文，不是元数据。

    `_format_task_output` 把 stdout 直接拼在同一行之后，其内容可以再带换行；不在此收尾，
    一条「成功但恰好打印了 `status: failed`」的后台命令会被标成失败行（review round 3
    MEDIUM，已在 Chromium 端到端复现）。
    """
    text = ("[Task bg-77]\nstatus: completed\nexit_code: 0\n"
            "stdout: checking things\nstatus: failed\nexit_code: 1")
    assert one("summarizeToolResult", "TaskOutput", text)["state"] == "ok"


def test_result_detects_browser_failure_prefixes():
    """浏览器族用方括号自有文案（`agent/tools/builtin/browser_*.py`）。

    后端 `_text_prefix_guess` 也没覆盖它们；漏掉会让「浏览器不可用 / URL 被拒」显示成成功。
    """
    for text in (
        "[Browser Error: page crashed]",
        "[Browser not available: browser service not configured]",
        "[URL denied: https://evil.example]",
    ):
        assert one("summarizeToolResult", "BrowserNavigate", text)["state"] == "error", text


def test_result_ignores_leading_blank_lines_when_detecting_failure():
    """结果可能以空行开头；失败判定必须看**首个非空行**。

    用 `firstLine` 会拿到空串而直接判 `ok`，于是「前后带空行的失败输出」在折叠行上
    显示成成功（review round 4 LOW）。
    """
    assert one("summarizeToolResult", "Bash", "\n\n[Error: boom]")["state"] == "error"
    assert one("summarizeToolResult", "Bash", "\nTraceback (most recent call last):\nx")["state"] == "error"
    # 全空白仍然是「空结果」，不算失败。
    assert one("summarizeToolResult", "Bash", "\n\n  \n")["state"] == "ok"


def test_result_detects_wait_timeout_wrapper():
    """`_wait_task_output` 超时返回 `[Task <id> timeout] [Task <id>]\\nstatus: running…`。

    此时任务可能仍在跑，但这次调用确实没拿到结果——折叠行要如实标出来，否则 wait 超时
    与「一切正常」在 UI 上无法区分（review round 4 LOW）。
    """
    text = ("[Task bg-9 timeout] [Task bg-9]\nstatus: running\nexit_code: None\nstdout: ")
    out = one("summarizeToolResult", "TaskOutput", text)
    assert out["state"] == "error"
    assert out["code"] == "timeout"


def test_bare_error_prefix_requires_a_single_line_result():
    """`Error: …` 与「工具返回文件内容」从首行无法区分。

    读一个首行正好写着 `Error:` 的文件不是失败；后端的工具失败文案都是**单行**消息，
    所以裸前缀只在结果整体就是一行时判失败。方括号前缀与 `Traceback` 不受此限。
    """
    file_body = "Error: this is just the first line of a file\nsecond line\nthird line"
    assert one("summarizeToolResult", "Read", file_body)["state"] == "ok"
    # 单行的真实工具失败仍然判失败。
    assert one("summarizeToolResult", "Read", "Error: file not found")["state"] == "error"
    # Traceback 是多行也判失败（该形态不可能是文件内容）。
    assert one("summarizeToolResult", "Bash",
               "Traceback (most recent call last):\n  File x, line 1")["state"] == "error"


def test_result_detects_nonzero_exit_code():
    # 文本形态（CLI / 其他工具的 stdout）同样要认。
    for text in ("exit code 1", "Exit code: 2\nstdout…", "[Exit 128] boom"):
        out = one("summarizeToolResult", "Bash", text)
        assert out["state"] == "error", text


def test_result_detects_sandbox_timeout_marker():
    assert one("summarizeToolResult", "Bash", "[Timeout after 30000ms] partial")["state"] == "error"


def test_result_detects_structured_timeout_json():
    payload = '{"exit_code": 0, "stdout": "", "stderr": "", "duration_ms": 1.0, "timed_out": true}'
    out = one("summarizeToolResult", "Bash", payload)
    assert out["state"] == "error"
    assert out["code"] == "timeout"


def test_result_zero_exit_code_is_not_error():
    out = one("summarizeToolResult", "Bash", "exit code 0\nall tests passed")
    assert out["state"] == "ok"
    assert one("summarizeToolResult", "Bash", "[Exit 0] ok")["state"] == "ok"


def test_result_summary_is_truncated_first_line():
    # 用方括号前缀（无歧义的失败标记）验证「失败摘要 = 首行且截断」；裸 `Error:` 前缀
    # 现在只在单行结果上判失败，见 test_bare_error_prefix_requires_a_single_line_result。
    out = one("summarizeToolResult", "Bash", "[Error: " + "z" * 400 + "]\nmore")
    assert out["summary"].endswith("…")
    assert len(out["summary"]) <= 120
    assert "more" not in out["summary"]


def test_result_tolerates_empty_and_missing_result():
    for value in ("", None):
        out = one("summarizeToolResult", "Bash", value)
        assert out["state"] == "ok"
        assert out["summary"] == ""


def test_result_does_not_flag_innocent_word_error():
    # 「0 errors」这类正常输出不能被误判成失败行，否则折叠行会整片变红。
    out = one("summarizeToolResult", "Bash", "0 errors, 12 passed")
    assert out["state"] == "ok"


# --- 行尾元数据 -------------------------------------------------------------


def test_char_meta_formats_counts():
    assert one("formatCharMeta", 42, 1) == "42 字符"
    assert one("formatCharMeta", 1500, 30) == "1.5k 字符 · 30 行"


def test_char_meta_uses_megabyte_unit_above_a_million():
    # `1048.6k 字符` 读不出量级；≥1e6 换成 M（grill R-G）。
    assert one("formatCharMeta", 1048576, 1) == "1.0M 字符"


def test_char_meta_handles_empty_result():
    assert one("formatCharMeta", 0, 0) == "空"


def test_char_meta_singular_line_omits_line_count():
    assert "行" not in one("formatCharMeta", 900, 1)


# --- 展开正文 ---------------------------------------------------------------


def test_body_text_truncates_with_note():
    out = one("formatBodyText", "a" * 50, 10)
    assert out["truncated"] is True
    assert out["text"] == "a" * 10


def test_body_text_keeps_short_text_intact():
    out = one("formatBodyText", "hello", 10)
    assert out["truncated"] is False
    assert out["text"] == "hello"


def test_body_text_handles_empty():
    out = one("formatBodyText", "", 10)
    assert out["text"] == ""
    assert out["truncated"] is False


def test_pretty_args_is_capped():
    """参数与结果共用同一条上限（grill Q3/R-C）。

    模型的 ``Write{content: ...}`` 参数可以到 MB 级；没上限就会在**看不见的**折叠
    body 里塞一个巨大的文本节点。真上限 200000 字符没法走命令行传进 node harness
    （Windows 命令行长度上限），所以这里注入小上限验证同一条截断路径。
    """
    small = one("prettyArgs", {"path": "a.py", "content": "x" * 100}, 100000)
    assert '"path": "a.py"' in small
    assert "已截断" not in small

    huge = one("prettyArgs", {"content": "x" * 5000}, 1000)
    assert len(huge) <= 1000 + 40
    assert "已截断" in huge


def test_pretty_args_defaults_to_the_module_limit():
    assert one("prettyArgs", "raw text") == "raw text"
