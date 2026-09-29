"""Name the exact carrier: capture the Python stack at the moment the abandoned
run's `finally` executes.  Expect `coro.close()` / `Task.__del__` frames.
"""
import asyncio
import gc
import sys
import traceback
import weakref

from agent.run_config import AgentMode
from agent.subagent.context import current_mode_ceiling, set_mode_ceiling


async def agent_loop_run_shape(tag):
    previous = current_mode_ceiling()
    set_mode_ceiling(AgentMode.BUILD)
    try:
        await asyncio.sleep(9999)
    finally:
        st = traceback.extract_stack()
        print(f"    [{tag}] FINALLY stack (innermost last):")
        for fr in st[-8:]:
            import os
            print(f"        {os.path.basename(fr.filename)}:{fr.lineno} {fr.name}  "
                  f"| {fr.line}")
        print(f"    [{tag}] ceiling here = {current_mode_ceiling()!r} (live ctx)")
        set_mode_ceiling(previous)


def make_abandoned():
    loop = asyncio.new_event_loop()
    task = loop.create_task(agent_loop_run_shape("abandoned"))
    loop.run_until_complete(asyncio.sleep(0.01))
    ref = weakref.ref(task)
    loop.close()
    del task
    return ref


async def later():
    set_mode_ceiling(AgentMode.READ_ONLY)
    gc.collect()
    await asyncio.sleep(0)


print(f"Python {sys.version.split()[0]}")
ref = make_abandoned()
asyncio.run(later())
print(f"abandoned task alive at end: {ref() is not None}")
