# Diagnosis: Windows/locale 编码缺陷类（会话持久化失效 + Hub 列表 500）

## Symptom

Windows（中文 locale = GBK/cp936）上跑 `uv run asterwynd web`：

- **Hub 会话列表恒 500**：`GET /api/sessions?workspace=...` 返回 `500 Internal Server Error`，页面上「Sessions」看不到任何会话。
- **会话保存静默失败**：服务端日志出现 `WARNING Failed to save session`，磁盘上只剩 `messages.json.tmp` / `snapshot.json.tmp`（从未提交成功），刷新/重启即丢会话。
- 排查过程中另见：benchmark 结果/manifest 读取在本机 `UnicodeDecodeError`；web 测试套件本机 47 条假红（#291 修掉 4 处编码站点后降到 9 条）。

## Reproduction

1. Windows（非 UTF-8 locale）上 `uv run asterwynd web --port 8000`。
2. 新建会话，发一条含 emoji 的消息（实测 `👋`，U+1F44B）。
3. 观察服务端日志：`WARNING Failed to save session` + `UnicodeEncodeError: 'gbk' codec can't encode character '\U0001f44b'`。
4. 调 `GET /api/sessions?workspace=<ws>`：`500`，traceback 落在 `agent/session.py:177` 的 `json.load(f)`（`UnicodeDecodeError: 'gbk' codec can't decode byte 0xa8`）。

## Evidence

**实测日志（本机 2026-10-04）**

```
WARNING Failed to save session
  File "agent/loop.py", line 652, in run            → self._save_session(...)
  File "agent/session.py", line 233, in _write      → json.dump([m.to_dict() ...], f, ensure_ascii=False)
UnicodeEncodeError: 'gbk' codec can't encode character '\U0001f44b' in position 38

ERROR: Exception in ASGI application
  File "web/server.py", line 331, in api_sessions   → session_manager._store_for(ws).list_sessions()
  File "agent/session.py", line 177, in list_sessions → msg_data = json.load(f)
UnicodeDecodeError: 'gbk' codec can't decode byte 0xa8 in position 47
```

**磁盘状态（同一时刻）**

| 会话 | 落盘 |
|------|------|
| `<ws>/.asterwynd/sessions/005f34abd229/` | 只有 `messages.json.tmp`(109 B) / `snapshot.json.tmp`(576 B) —— 从未保存成功 |
| `<ws>/.asterwynd/sessions/e8673fe28291/` | `messages.json`(20 KB) 保存成功 —— 而正是它让列表接口 500 |

**站点清点**（`Select-String` 全仓扫描，排除 `rb/wb/ab`、`os.open`、fd 形态与 `async def ..._open` 误报）

| 位置 | 数量 | 性质 |
|------|------|------|
| `agent/session.py:119/121/159/176/230/232` | 6 | 生产：会话存储读写 |
| `agent/main.py:952/968/1096/1097` | 4 | 生产：benchmark 结果/manifest/record 的 `read_text()` |
| `tests/**` 的 `subprocess(..., text=True)` | 33（已修 4） | 测试：本机假红 |

**为什么长期没暴露**

- CI 两个 job 都是 `ubuntu-latest`：Linux locale 即 UTF-8 ⇒ 未指定编码与显式 UTF-8 **行为一致**，这类缺陷在现网 CI 上**不可能变红**（不是「漏测某个用例」，是整类信号缺失）。
- 本机 Windows 上确实是红的，但被长期归类为「环境性失败、pristine 同样失败」并记录容忍（本 change 之前的 `reviews/acceptance-evidence.md` 里就写着 47 条环境性红灯）。**CI 盲区 + 容忍 ⇒ 零防护。**

## Root Cause

1. **直接原因**：`agent/session.py` 的本地文件 I/O 未显式指定编码，`open()` 按进程 locale（Windows 中文机器上为 GBK）编解码，而存储格式是 UTF-8。写入路径遇非 GBK 可编码字符（emoji）抛 `UnicodeEncodeError`；读取路径遇非 GBK 可解码字节抛 `UnicodeDecodeError`。`agent/main.py` 的 4 处 `read_text()` 同类。
2. **放大原因**：`list_sessions()` 让**单条**会话的解码失败冒泡成**整个列表接口** 500 —— 单点失败放大为全局失败（一个坏文件打掉整个 Hub）。
3. **系统性原因**：缺「机械可拦」的守卫 + CI 缺少非 UTF-8 locale 信号源，于是同类缺陷可以反复新增而不被发现。

## Recommended Direction

1. **边界显式**（D1）：`agent/session.py` 6 处 + `agent/main.py` 4 处补 `encoding="utf-8"`；并把 `UnicodeDecodeError` 纳入捕获（它**不是** `OSError`，此前直接冒泡）。读侧**不**用 `errors="replace"`：那会把半损内容当完整会话交付。
2. **单条降级**（D4）：`list_sessions()` 遇到不可解码/损坏的会话文件 SHALL 跳过该条并**如实标注**（不静默、不 500），返回其余可用会话。
3. **L1 机械守卫**：新增全仓静态扫描测试（沿用 `tests/web_tests/test_python_version_compat.py` 的形态），命中「`open`/`read_text`/`write_text` 缺 encoding」与「`subprocess(text=True)` 既无 `encoding=` 也无 `errors=`」即失败并列出 `file:line`，配显式白名单 + 理由。
4. **L2 行为回归**：新增 `tests/agent/test_session_encoding.py` —— emoji/CJK 往返；**在 `LC_ALL=C` + `PYTHONCOERCECLOCALE=0` 子进程里**复现非 UTF-8 locale 条件（Linux 上等价于 Windows 的 GBK，且更严格）；`PYTHONWARNDEFAULTENCODING=1` 下断言无 `EncodingWarning`（PEP 597）；**两条**列表降级分支（快照坏 / 消息坏，且脏数据载荷必须真的非 UTF-8）；Hub 层在 `tests/web_tests/test_multi_session.py` 补 2 条（含 emoji 的会话 → 接口 200 且出现在列表里；单条损坏 → 200 + `damaged`/`reason`）。
5. **L3 CI 覆盖**：`validate` job 增加 C-locale 步骤（便宜、直接守编码类）+ 新增 `windows-latest` job 跑子集（覆盖 Windows 路径语义类，现有 9 条红灯正属此类）。
6. **纪律**：`docs/testing-guide.md` 写明「本地 I/O 一律显式 UTF-8；本机 Windows 红灯 MUST 修或进白名单，SHALL NOT 长期当环境噪声」。

## Regression Tests

| 层级 | 用例 | 判据 |
|------|------|------|
| L1 静态 | `test_encoding_hygiene.py` | 全仓扫描无未白名单的裸 `open`/`read_text`/`write_text`/`text=True`；offenders 按 `file:line` 全列 |
| L2 往返 | `test_session_roundtrip_with_emoji_and_cjk` | 含 `👋`/中文/生僻字的会话 `save → load` 内容逐字一致 |
| L2 非 UTF-8 locale | `test_roundtrip_survives_non_utf8_locale`（子进程 `LC_ALL=C` + `PYTHONCOERCECLOCALE=0`） | 往返成功；**在 Linux CI 上也能抓到**「去掉 encoding」的回归 |
| L2 默认编码告警 | 同文件，`PYTHONWARNDEFAULTENCODING=1` 子进程断言无 `EncodingWarning` | 任何新引入的「依赖 locale 默认编码」在运行时可见 |
| L2 列表降级 | `test_list_sessions_skips_undecodable_file` | 损坏条目被跳过并标注，其余会话仍返回，**不抛异常** |
| L2 接口 | `test_api_sessions_returns_200_with_emoji_session`（在 `tests/web_tests/test_multi_session.py`） | 某会话含 emoji 时 `GET /api/sessions` = 200 且含该会话元数据 |
| L2 接口 | `test_api_sessions_marks_damaged_entry_without_failing` | 单条损坏 → 仍 200，该条带 `damaged` + `reason` |
| L2 子进程 | `test_benchmark_smoke_has_no_decode_crash`（人工复核：`asterwynd benchmark … --agent fake` 的 `UnicodeDecodeError` 计数 = 0） | 捕获文本的子进程不再因解码崩掉（此前一次跑 16 处） |
| 变异 | 去掉任一 `encoding=` → L1 红；去掉列表降级 → L2 红；接口容错去掉 → web 用例红 | 三条变异各杀对应用例 |
