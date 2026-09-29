"""Minimal deterministic reproduction of issue #261.

Mechanism
---------
``AgentLoop.run`` brackets each run with mount A:

    previous = current_mode_ceiling()
    set_mode_ceiling(mode)          # loop.py:570
    try:  ...run body...
    finally: set_mode_ceiling(previous)   # loop.py:598  <-- plain `set`

A subagent run executes in an independent Task created by
``SubAgentManager._start_task`` (``manager.py:967``).  Tests routinely ABANDON
such tasks (never await them to a terminal state); the next test then starts, and
the abandoned Task is eventually deallocated by GC.

``Task.__del__`` calls ``coro.close()``.  ``coro.close()`` throws ``GeneratorExit``
into the coroutine at its suspension point, which unwinds EVERY nested ``finally``
in the await chain -- including ``AgentLoop.run``'s mount-A restore.

Crucially, ``coro.close()`` is a plain method call: it does NOT install the
task's own Context.  The unwinding therefore runs in whatever Context is
*currently running* -- i.e. the LATER test's task context.  ``ContextVar.set``
writes to the running context, so the stale restore overwrites the live run's
ceiling with ``None``.  The scheduler then dispatches with ``ceiling=None``,
``SubAgentManager._parent_mode()`` falls back to the static ``parent_mode``
(BUILD in the failing test), and the node is frozen as ``build`` -> assertion
``'build' == 'read_only'`` fails.
"""
import asyncio
import gc
import sys
import weakref

from agent.run_config import AgentMode
from agent.subagent.context import current_mode_ceiling, set_mode_ceiling

_polluted = []


async def agent_loop_run_shape(tag):
    """Exact shape of AgentLoop.run's mount A (loop.py:563-598)."""
    previous = current_mode_ceiling()
    set_mode_ceiling(AgentMode.BUILD)
    try:
        await asyncio.sleep(9999)          # a real run suspends at its LLM await
    finally:
        print(f"    [{tag}] finally ran; ceiling here = {current_mode_ceiling()!r} "
              f"-> writing {previous!r}")
        set_mode_ceiling(previous)         # loop.py:598


def create_abandoned_task():
    """Create the run's Task the way tests leave it: started, never awaited."""
    loop = asyncio.new_event_loop()
    task = loop.create_task(agent_loop_run_shape("abandoned-run"))
    loop.run_until_complete(asyncio.sleep(0.01))   # let mount A install, then suspend
    ref = weakref.ref(task)
    loop.close()                                    # loop gone; task still pending
    del task                                        # manager's ref also gone
    return ref


async def later_test():
    """A later test's root run: read_only session, mount A active."""
    set_mode_ceiling(AgentMode.READ_ONLY)
    print(f"    [later test] mount A installed: ceiling = {current_mode_ceiling()!r}")

    gc.collect()                                    # dealloc the abandoned Task HERE
    await asyncio.sleep(0)

    ceiling = current_mode_ceiling()
    print(f"    [later test] ceiling now     : {ceiling!r}")
    # What SubAgentManager._parent_mode() would return for a declared-build node:
    effective = ceiling if ceiling is not None else AgentMode.BUILD   # static fallback
    print(f"    [later test] node would freeze as: {effective.value}")
    if effective is not AgentMode.READ_ONLY:
        _polluted.append(effective)


def main():
    print(f"Python {sys.version.split()[0]}")
    ref = create_abandoned_task()
    print(f"  abandoned task alive before later test: {ref() is not None}")
    asyncio.run(later_test())
    print()
    if _polluted:
        print(f">>> REPRODUCED: live read_only ceiling was clobbered; node froze as "
              f"{_polluted[0].value!r} (expected 'read_only')")
        return 1
    print(">>> NOT reproduced")
    return 0


sys.exit(main())
