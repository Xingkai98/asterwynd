from agent.workflow.dispatcher import DispatchResult, WorkflowDispatcher
from agent.workflow.manager import WorkflowManager
from agent.workflow.models import (
    DEFAULT_ROUTING,
    GATE_SUB_STATE,
    PHASE_ORDER,
    PHASE_SUB_STATES,
    PHASE_TO_ROLE,
    PHASES,
    ActorType,
    Blocker,
    CurrentAgent,
    Decision,
    Executor,
    LastGate,
    NextHints,
    Phase,
    PhaseRouting,
    RoleAgentType,
    SessionMode,
    StateSnapshot,
    SubState,
    Transition,
    Trigger,
)
from agent.workflow.role_registry import (
    RoleAgentConfig,
    build_role_configs,
    build_subagent_task,
    get_role_config,
)
from agent.workflow.routing import (
    RoutingConfigError,
    build_routing_config_prompt,
    get_routing_for_phase,
    load_global_defaults,
    merge_routing,
)
from agent.workflow.state_machine import (
    StateMachineError,
    get_legal_targets,
    init_handoff_json,
    load_handoff_json,
    save_handoff_json,
    validate_transition,
)

__all__ = [
    # Manager
    "WorkflowManager",
    "WorkflowDispatcher",
    "DispatchResult",
    # Errors
    "StateMachineError",
    "RoutingConfigError",
    # Types
    "Phase",
    "SubState",
    "Trigger",
    "Decision",
    "RoleAgentType",
    "Executor",
    "SessionMode",
    "ActorType",
    # Constants
    "PHASES",
    "PHASE_SUB_STATES",
    "PHASE_TO_ROLE",
    "PHASE_ORDER",
    "GATE_SUB_STATE",
    "DEFAULT_ROUTING",
    # Dataclasses
    "StateSnapshot",
    "Transition",
    "CurrentAgent",
    "LastGate",
    "Blocker",
    "PhaseRouting",
    "NextHints",
    "RoleAgentConfig",
    # State machine
    "validate_transition",
    "get_legal_targets",
    "init_handoff_json",
    "load_handoff_json",
    "save_handoff_json",
    # Routing
    "load_global_defaults",
    "merge_routing",
    "get_routing_for_phase",
    "build_routing_config_prompt",
    # Role registry
    "build_role_configs",
    "get_role_config",
    "build_subagent_task",
]
