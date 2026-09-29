"""Same as min_repro_261 but the abandoned run uses the PROPOSED restore shape
(guarded `reset(token)`) instead of plain `set(previous)`.  If the mechanism is
right, the live ceiling must survive.
"""
import asyncio
import gc
import sys
import weakref

from agent.subagent.context import (
    current_mode_ceiling,
    reset_mode_ceiling,
    set_mode_ceiling,
)
from agent.run_config import AgentMode

_polluted = []


async def run_shape_FIXED(tag):
    """AgentLoop.run with the proposed guarded reset(token)."""
    token = set_mode_ceiling(AgentMode.BUILD)      # mount A install
    try:
        await asyncio.sleep(9999)
    finally:
        print(f"    [{tag}] finally ran; ceiling here = {current_mode_ceiling()!r}")
        try:
            reset_mode_ceiling(token)
            print(f"    [{tag}] reset(token) OK -> ceiling = {current_mode_ceiling()!r}")
        except ValueError as exc:
            print(f"    [{tag}] reset(token) raised {type(exc).__name__}: skipped "
                  f"(cross-context teardown) -> live ceiling untouched")


async def run_shape_CURRENT(tag):
    """AgentLoop.run with the current plain `set(previous)` (control)."""
    previous = current_mode_ceiling()
    set_mode_ceiling(AgentMode.BUILD)
    try:
        await asyncio.sleep(9999)
    finally:
        print(f"    [{tag}] finally ran; ceiling here = {current_mode_ceiling()!r} "
              f"-> writing {previous!r}")
        set_mode_ceiling(previous)


def create_abandoned_task(fn):
    loop = asyncio.new_event_loop()
    task = loop.create_task(fn("abandoned"))
    loop.run_until_complete(asyncio.sleep(0.01))
    ref = weakref.ref(task)
    loop.close()
    del task
    return ref


async def later_test():
    set_mode_ceiling(AgentMode.READ_ONLY)
    gc.collect()
    await asyncio.sleep(0)
    ceiling = current_mode_ceiling()
    effective = ceiling if ceiling is not None else AgentMode.BUILD
    print(f"    [later test] ceiling={ceiling!r} -> node freezes as {effective.value}")
    if effective is not AgentMode.READ_ONLY:
        _polluted.append(effective)


def main(which):
    print(f"=== {which} ===")
    fn = run_shape_FIXED if which == "FIXED" else run_shape_CURRENT
    ref = create_abandoned_task(fn)
    asyncio.run(later_test())
    print(f"    polluted: {bool(_polluted)}")
    print()
    return 1 if _polluted else 0


rc = main(sys.argv[1] if len(sys.argv) > 1 else "CURRENT")
sys.exit(rc)
