"""issue #264 设计点取证：三个待论证点的可执行证据（纯 contextvars，无生产类）。

不改任何生产代码；只回答 change 的 `design.md` 里 D1–D3 三个设计点：

- **D1（API 形态）**：`set()` 返回的 token 在**从未 set 过**（default 生效）与
  **set 过**两种情况下是否都能正常 `reset`？→ 结论：都能。
- **D2（`_NOOP` vs `None` 哨兵）**：`contextvars.reset(token)` 跨上下文抛
  `ValueError` 的判据是 **Context 身份**还是**默认值**？→ 结论：身份。故
  sandbox sink（default `_NOOP`）与 mode_ceiling（default `None`）行为**一致**。
- **D3（跨上下文对照）**：同一个「遗留 task 在后续上下文里被终结」模式，
  `set(previous)` 会污染、守护式 `reset(token)` 不会。

退出码 0（本脚本是取证，不是复现，不区分成败）。
"""
from __future__ import annotations

import asyncio
import contextvars
import gc
import sys

_NOOP = object()
print(f"Python {sys.version.split()[0]}  contextvars 设计点取证\n")

# ================= D1 / token 可用性 =================
print("D1: token 可用性（default = _NOOP 哨兵）")
v = contextvars.ContextVar("v", default=_NOOP)
print("  从未 set            -> get() is default:", v.get() is _NOOP)
t1 = v.set("A")
print("  首次 set 返回 token :", t1 is not None)
v.reset(t1)
print("  reset(t1)           -> get() is default again:", v.get() is _NOOP)

t2, t3 = v.set("B"), v.set("C")
v.reset(t3)
print("  嵌套 reset(inner)   -> get() == 'B':", v.get() == "B")
v.reset(t2)
print("  嵌套 reset(outer)   -> get() is default:", v.get() is _NOOP)
try:
    v.reset(t2)
    print("  二次 reset          -> NO ERROR (!)")
except Exception as exc:  # noqa: BLE001
    print(f"  二次 reset          -> {type(exc).__name__}（token 已用过；注意**不是** ValueError）")
print("  结论：token 与「此前是否 set 过」无关，两种情况都能 reset，")
print("        reset 恢复的是那次 set **之前**生效的值（未 set 过时即 default）。")
print("        注意二次 reset 抛 RuntimeError，`except ValueError` 兜不住它——")
print("        但本 change 的 token 由本协程自己创建、至多消费一次，不受影响。\n")

# ================= D2 / 哨兵值不进判据 =================
print("D2: 跨上下文 reset —— _NOOP-defaulted vs None-defaulted")
sink_var = contextvars.ContextVar("sink", default=_NOOP)   # 镜像 _current_sink
ceil_var = contextvars.ContextVar("ceil", default=None)    # 镜像 _mode_ceiling
tokens = {"sink": sink_var.set("RunA-sink"), "ceil": ceil_var.set("RunA-ceiling")}


def _finalise_elsewhere():
    out = {}
    for name, var in (("sandbox sink (default _NOOP)", sink_var),
                      ("mode_ceiling (default None)", ceil_var)):
        key = "sink" if "sandbox" in name else "ceil"
        try:
            var.reset(tokens[key])
            out[name] = f"reset OK -> {var.get()!r}  （写进了本上下文 = 污染）"
        except Exception as exc:  # noqa: BLE001
            out[name] = f"{type(exc).__name__} -> 跳过，未写入"
    return out


for k, val in contextvars.copy_context().run(_finalise_elsewhere).items():
    print(f"  {k}: {val}")
print("  结论：两个哨兵**行为完全一致**——都因 Context 身份不同抛 ValueError。")
print("        reset 校验的是 Context 身份，与 default 的值类型无关；")
print("        故守护式 reset 在 sandbox sink 上不会产生与 mode_ceiling 不同的行为，")
print("        `_NOOP` 的「丢弃事件」语义也不受影响（恢复的就是 set 之前那个值）。\n")

# ================= D3 / set(prev) vs 守护式 reset =================
print("D3: 遗留 task 终结路径 —— set(prev) 写活跃上下文；守护式 reset 跳过")
LIVE = contextvars.ContextVar("live_sink", default=_NOOP)
MODE = {"v": "set", "tok": None}


async def _hang():
    try:
        await asyncio.sleep(9999)
    finally:
        if MODE["v"] == "set":
            LIVE.set("STALE-SINK")            # agent/loop.py:600 现状
        else:
            try:
                LIVE.reset(MODE["tok"])       # 拟采用的守护式 reset
            except ValueError:
                pass


for mode in ("set", "reset"):
    MODE["v"] = mode
    loop = asyncio.new_event_loop()

    async def _prime():
        MODE["tok"] = LIVE.set("RunA-sink")   # token 建在**该 task 自己的**上下文
        task = asyncio.create_task(_hang())
        await asyncio.sleep(0.01)
        return task

    task = loop.run_until_complete(_prime())
    loop.close()
    del loop, task
    LIVE.set("LIVE-sink")                     # 后续 run 装上自己的 sink
    gc.collect()                              # 遗留 task 在此刻被终结
    polluted = LIVE.get() == "STALE-SINK"
    tag = "POLLUTED（活跃 run 的事件会串写/丢失）" if polluted else "clean（活跃 sink 完好）"
    print(f"  形态={mode:5s} -> 终结后活跃 sink: {LIVE.get()!r}  [{tag}]")
print("  结论：同一条遗留终结路径，现状 `set(prev)` 污染、守护式 reset 不污染。")
print("        （生产侧该行是 agent/loop.py:600 的 `set_sandbox_sink(previous_sandbox_sink)`。）")
