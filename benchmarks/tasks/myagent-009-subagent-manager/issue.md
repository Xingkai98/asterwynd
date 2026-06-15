# Implement SubAgentManager with ParentChannelHook

The `ParentChannel` protocol exists but there is no manager to handle sub-agent lifecycles or a hook to route messages between parent and child agents during active turns.

## Task

Implement two components:

### SubAgentManager (`agent/subagent/manager.py`)
1. Manage child agent lifecycles: spawn, monitor, terminate
2. Children inherit the parent's tool registry and memory manager
3. Spawn creates a new agent loop with a subset of tools
4. Track active child agents by ID

### ParentChannelHook (`agent/subagent/parent_channel_hook.py`)
1. Implement the `Hook` protocol
2. Route messages between parent and children through the hook system
3. Inject child agent results into the parent's message stream mid-turn

## Requirements

- Create both files under `agent/subagent/`
- Follow the existing `Hook` protocol in `agent/hooks/manager.py`
- Sub-agents must run as background tasks (not block the parent)
- Results from completed children are injected via the hook system
