#!/usr/bin/env python3
"""
Asterwynd CLI 入口模块

用法:
    asterwynd                         # 交互 REPL
    asterwynd run "你好"              # 单轮执行
    asterwynd web --port 8000         # Web UI
    asterwynd benchmark benchmarks/tasks --agent fake
"""
import asyncio
import inspect
import json
import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
import platformdirs
import typer

load_dotenv()

from agent.approval import ApprovalHandler, CliApprovalHandler
from agent.loop import AgentLoop
from agent.commands import CommandContext, build_default_slash_command_registry
from agent.commands.init import write_aster_md
from agent.config import ConfigError, ConfigOverrides, AsterwyndConfig, load_config
from agent.message import Message
from agent.openai_llm import OpenAILLM
from agent.anthropic_llm import AnthropicLLM
from agent.run_config import AgentMode, AgentRunConfig, ModePolicy, parse_agent_mode
from agent.subagent.manager import SubAgentManager
from agent.tools.factory import build_default_tool_registry
from agent.tools.sandbox import SandboxExecutor
from agent.workspace_policy import WorkspacePolicy
from agent.background import BackgroundTaskManager
from agent.session import SessionSnapshot, SessionStore
from agent.hooks.manager import HookManager
from agent.hooks.builtin import LoggingHook, TracingHook
from agent.memory.manager import MemoryManager
from agent.memory.persistent import PersistentMemory
from agent.llm import LLM
from agent.mcp import build_mcp_manager
from agent.run_identity import new_run_id, new_session_id
from agent.skills import SkillRuntime
from agent.tool_result_display import summarize_tool_result
from agent.branding import BRAND_NAME, render_tui_banner

LOG_DIR = platformdirs.user_log_path("asterwynd")
LOG_FILE = LOG_DIR / f"asterwynd-{__import__('datetime').datetime.now().strftime('%Y%m%d-%H%M%S')}.log"
_LOG_LEVEL = getattr(logging, os.environ.get("ASTERWYND_LOG_LEVEL", "INFO").upper(), logging.INFO)
logger = logging.getLogger("asterwynd.cli")


def _setup_logging() -> None:
    """Initialize logging. File handler degrades gracefully on read-only filesystems."""
    handlers: list[logging.Handler] = [logging.StreamHandler()]
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        handlers.append(
            RotatingFileHandler(LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=5, encoding="utf-8")
        )
    except OSError:
        pass
    logging.basicConfig(
        level=_LOG_LEVEL,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
        handlers=handlers,
    )

app = typer.Typer()
workflow_app = typer.Typer(help="Workflow control")
workflow_manage_app = typer.Typer(help="Managed roots")
workflow_gate_app = typer.Typer(help="Human gate")
workflow_app.add_typer(workflow_manage_app, name="manage")
workflow_app.add_typer(workflow_gate_app, name="gate")
app.add_typer(workflow_app, name="workflow")


def _workflow_db_path(db: Path | None) -> Path:
    if db is not None:
        return db
    return platformdirs.user_data_path("asterwynd") / "workflow-control.sqlite3"


def _workflow_roots_path(roots_file: Path | None) -> Path:
    if roots_file is not None:
        return roots_file
    return platformdirs.user_config_path("asterwynd") / "workflow-roots.json"


def _workflow_orchestrator(db: Path | None):
    from workflow_control import (
        SQLiteEventStore,
        SQLiteEventStoreConfig,
        WorkflowOrchestrator,
        WorkflowOrchestratorConfig,
        default_coding_agent_template,
    )

    store = SQLiteEventStore(SQLiteEventStoreConfig(db_path=_workflow_db_path(db)))
    template = default_coding_agent_template()
    return WorkflowOrchestrator(
        WorkflowOrchestratorConfig(store=store, template=template),
    )


def _workflow_actor(actor_id: str, *, human: bool = False):
    from workflow_control import Actor, ActorKind

    if human:
        return Actor(
            kind=ActorKind.HUMAN,
            actor_id=actor_id,
            approval_capability=True,
        )
    return Actor(kind=ActorKind.AGENT, actor_id=actor_id)


def _workflow_snapshot_payload(snapshot) -> dict:
    return {
        "workflow_id": snapshot.workflow_id,
        "version": snapshot.version,
        "state": {
            "phase": snapshot.state.phase,
            "sub_state": snapshot.state.sub_state,
        },
    }


def _workflow_enter_payload(result) -> dict:
    payload = _workflow_snapshot_payload(result.snapshot)
    payload["waiting_for_human"] = result.waiting_for_human
    if result.work_item is None:
        payload["work_item"] = None
    else:
        payload["work_item"] = {
            "work_item_id": result.work_item.work_item_id,
            "workflow_id": result.work_item.workflow_id,
            "state": {
                "phase": result.work_item.state.phase,
                "sub_state": result.work_item.state.sub_state,
            },
            "allowed_actions": list(result.work_item.allowed_actions),
        }
    return payload


def _echo_json_or_text(payload: dict, json_output: bool) -> None:
    if json_output:
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    typer.echo(
        f"{payload['workflow_id']} v{payload['version']} "
        f"{payload['state']['phase']}.{payload['state']['sub_state']}"
    )


def build_llm(provider: str, model: Optional[str] = None) -> LLM:
    if model is None:
        model = os.environ.get("ASTERWYND_MODEL")
    kwargs = {}
    if model is not None:
        kwargs["model"] = model
    if provider == "anthropic":
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            typer.echo("Error: ANTHROPIC_API_KEY not set", err=True)
            raise SystemExit(1)
        base_url = os.environ.get("ANTHROPIC_BASE_URL", "https://api.anthropic.com")
        llm = AnthropicLLM(api_key=api_key, base_url=base_url, **kwargs)
        llm.stream = _streaming_enabled()
        return llm
    else:
        # openai (default)
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            typer.echo("Error: OPENAI_API_KEY not set", err=True)
            raise SystemExit(1)
        base_url = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
        llm = OpenAILLM(api_key=api_key, base_url=base_url, **kwargs)
        llm.stream = _streaming_enabled()
        return llm


def _streaming_enabled() -> bool:
    value = os.environ.get("ASTERWYND_STREAMING", "enabled").strip().lower()
    return value not in {"0", "false", "off", "disabled", "no"}


def _normalize_user_mode(mode: str | AgentMode) -> str:
    if isinstance(mode, AgentMode):
        return mode.value
    try:
        return parse_agent_mode(mode).value
    except ValueError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise SystemExit(1) from exc


def _load_cli_config(
    config_path: Optional[Path],
    *,
    mode: str | None = None,
    benchmark_parallel: int | None = None,
    benchmark_timeout_seconds: int | None = None,
) -> AsterwyndConfig:
    try:
        return load_config(
            config_path=config_path,
            cli_overrides=ConfigOverrides(
                default_mode=mode,
                benchmark_parallel=benchmark_parallel,
                benchmark_timeout_seconds=benchmark_timeout_seconds,
            ),
        )
    except ConfigError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise SystemExit(1) from exc


def build_agent(
    model: Optional[str] = None,
    provider: str = "openai",
    mode: str | AgentMode = AgentMode.BUILD,
    config: AsterwyndConfig | None = None,
    approval_handler: ApprovalHandler | None = None,
) -> AgentLoop:
    if config is not None and config.mcp.servers:
        raise RuntimeError("build_agent with MCP config requires build_agent_async")
    return _build_agent_core(
        model=model,
        provider=provider,
        mode=mode,
        config=config,
        approval_handler=approval_handler,
        mcp_manager=None,
    )


async def build_agent_async(
    model: Optional[str] = None,
    provider: str = "openai",
    mode: str | AgentMode = AgentMode.BUILD,
    config: AsterwyndConfig | None = None,
    approval_handler: ApprovalHandler | None = None,
) -> AgentLoop:
    config = config or AsterwyndConfig()
    mcp_manager = await build_mcp_manager(config)
    return _build_agent_core(
        model=model,
        provider=provider,
        mode=mode,
        config=config,
        approval_handler=approval_handler,
        mcp_manager=mcp_manager,
    )


def _sessions_root(workspace_root: Path) -> str:
    return str(workspace_root / ".asterwynd" / "sessions")


def _load_resume_snapshot(session_id: str, config: AsterwyndConfig | None = None) -> SessionSnapshot | None:
    store = SessionStore(sessions_root=_sessions_root(Path.cwd()))
    snapshot = store.load(session_id)
    if snapshot is None:
        typer.echo(f"Error: Session {session_id} not found or cannot be restored.", err=True)
        raise SystemExit(1)
    return snapshot


def _build_agent_core(
    *,
    model: Optional[str] = None,
    provider: str = "openai",
    mode: str | AgentMode = AgentMode.BUILD,
    config: AsterwyndConfig | None = None,
    approval_handler: ApprovalHandler | None = None,
    mcp_manager=None,
) -> AgentLoop:
    config = config or AsterwyndConfig()
    llm = build_llm(provider, model)
    run_config = AgentRunConfig(mode=parse_agent_mode(_normalize_user_mode(mode)))
    workspace_policy = WorkspacePolicy(
        command_denylist=config.tools.command_denylist,
    )
    persistent_memory = PersistentMemory(workspace_policy.workspace_root)

    registry = build_default_tool_registry(
        policy=workspace_policy,
        mode_policy=ModePolicy(
            run_config,
            deny_tools_by_mode=config.deny_tools_by_mode(),
            permission_profiles_by_mode=config.permission_profiles_by_mode(),
        ),
        ignore_patterns=config.tools.ignore_patterns,
        code_intelligence_config=config.tools.code_intelligence,
        web_search_config=config.tools.web_search,
        browser_config=config.tools.browser,
        mcp_manager=mcp_manager,
        persistent_memory=persistent_memory,
    )

    hooks = HookManager([
        LoggingHook(verbose=False),
        TracingHook(),
    ])

    memory = MemoryManager(max_tokens=80_000)
    subagent_manager = SubAgentManager(
        llm=llm,
        config=config,
        workspace_policy=workspace_policy,
        parent_mode=run_config.mode,
    )
    skill_runtime = SkillRuntime.from_roots(config.skills.roots)

    sandbox = SandboxExecutor()
    background_manager = BackgroundTaskManager(sandbox=sandbox)
    session_store = SessionStore(
        sessions_root=_sessions_root(workspace_policy.workspace_root)
    )

    return AgentLoop(
        llm=llm,
        tool_registry=registry,
        hooks=hooks,
        memory=memory,
        persistent_memory=persistent_memory,
        subagent_manager=subagent_manager,
        expose_subagent_tools=True,
        run_config=run_config,
        tool_result_display=config.tools.display,
        skill_runtime=skill_runtime,
        approval_handler=approval_handler,
        mcp_manager=mcp_manager,
        background_manager=background_manager,
        session_store=session_store,
    )


@app.command()
def init(
    path: Optional[str] = typer.Option(None, "--path", help="目标目录（不指定则用当前工作目录）"),
):
    """在当前目录生成 ASTER.md 项目指令文件"""
    cwd = Path(path) if path else None
    try:
        msg = write_aster_md(cwd=cwd)
        typer.echo(msg)
    except Exception as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise SystemExit(1)


@workflow_app.command("enter")
def workflow_enter(
    workflow: str = typer.Option(..., "--workflow", help="Workflow ID"),
    db: Optional[Path] = typer.Option(None, "--db", help="Workflow SQLite path"),
    actor: str = typer.Option("agent", "--actor", help="Actor ID"),
    json_output: bool = typer.Option(False, "--json", help="JSON 输出"),
):
    """进入 workflow，必要时创建 exploration workflow，并返回 WorkItem。"""
    orchestrator = _workflow_orchestrator(db)
    result = orchestrator.enter(workflow, _workflow_actor(actor))
    _echo_json_or_text(_workflow_enter_payload(result), json_output)


@workflow_app.command("status")
def workflow_status(
    workflow: str = typer.Option(..., "--workflow", help="Workflow ID"),
    db: Optional[Path] = typer.Option(None, "--db", help="Workflow SQLite path"),
    json_output: bool = typer.Option(False, "--json", help="JSON 输出"),
):
    """查看 workflow 当前状态。"""
    orchestrator = _workflow_orchestrator(db)
    result = orchestrator.status(workflow)
    _echo_json_or_text(_workflow_snapshot_payload(result.snapshot), json_output)


@workflow_app.command("report")
def workflow_report(
    workflow: str = typer.Option(..., "--workflow", help="Workflow ID"),
    work_item_id: str = typer.Option(..., "--work-item-id", help="WorkItem ID"),
    expected_version: int = typer.Option(..., "--expected-version", help="Expected workflow version"),
    summary: str = typer.Option("", "--summary", help="Work summary"),
    db: Optional[Path] = typer.Option(None, "--db", help="Workflow SQLite path"),
    actor: str = typer.Option("agent", "--actor", help="Actor ID"),
    json_output: bool = typer.Option(False, "--json", help="JSON 输出"),
):
    """提交 WorkResult，由 orchestrator 决定下一状态。"""
    from workflow_control import WorkResult

    orchestrator = _workflow_orchestrator(db)
    result = orchestrator.report(
        workflow_id=workflow,
        actor=_workflow_actor(actor),
        work_item_id=work_item_id,
        result=WorkResult(summary=summary),
        expected_version=expected_version,
    )
    _echo_json_or_text(_workflow_snapshot_payload(result.snapshot), json_output)


@workflow_gate_app.command("approve")
def workflow_gate_approve(
    workflow: str = typer.Option(..., "--workflow", help="Workflow ID"),
    db: Optional[Path] = typer.Option(None, "--db", help="Workflow SQLite path"),
    user: str = typer.Option("human", "--user", help="Human user ID"),
    message: str = typer.Option("ok", "--message", help="Raw approval message"),
    json_output: bool = typer.Option(False, "--json", help="JSON 输出"),
):
    """可信 CLI 人工批准当前 gate。"""
    from workflow_control import GateApprovalTokenMatcher

    if os.environ.get("ASTERWYND_WORKFLOW_TRUSTED_HOST") != "1":
        typer.echo("Error: workflow gate approve requires trusted host context", err=True)
        raise SystemExit(1)
    if os.environ.get("ASTERWYND_WORKFLOW_AGENT_CONTEXT") == "1":
        typer.echo("Error: workflow gate approve is not available from agent context", err=True)
        raise SystemExit(1)

    orchestrator = _workflow_orchestrator(db)
    status = orchestrator.status(workflow)
    if not GateApprovalTokenMatcher().matches(message):
        typer.echo("Error: approval message is not an allowed exact token", err=True)
        raise SystemExit(1)
    result = orchestrator.approve_gate(
        workflow_id=workflow,
        actor=_workflow_actor(user, human=True),
        raw_user_message=message,
        expected_version=status.snapshot.version,
    )
    _echo_json_or_text(_workflow_snapshot_payload(result.snapshot), json_output)


def _load_workflow_roots(path: Path) -> list[str]:
    if not path.exists():
        return []
    return list(json.loads(path.read_text(encoding="utf-8")).get("managed_roots", []))


def _save_workflow_roots(path: Path, roots: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"managed_roots": roots}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _emit_roots(path: Path, json_output: bool) -> None:
    roots = _load_workflow_roots(path)
    if json_output:
        typer.echo(json.dumps({"managed_roots": roots}, ensure_ascii=False, indent=2))
        return
    for root in roots:
        typer.echo(root)


@workflow_manage_app.command("add")
def workflow_manage_add(
    root: Path = typer.Argument(..., help="Managed workspace root"),
    roots_file: Optional[Path] = typer.Option(None, "--roots-file", help="Managed roots JSON path"),
    json_output: bool = typer.Option(False, "--json", help="JSON 输出"),
):
    """添加受管项目根目录。"""
    path = _workflow_roots_path(roots_file)
    roots = _load_workflow_roots(path)
    canonical = str(root.resolve())
    if canonical not in roots:
        roots.append(canonical)
        roots.sort()
    _save_workflow_roots(path, roots)
    _emit_roots(path, json_output)


@workflow_manage_app.command("list")
def workflow_manage_list(
    roots_file: Optional[Path] = typer.Option(None, "--roots-file", help="Managed roots JSON path"),
    json_output: bool = typer.Option(False, "--json", help="JSON 输出"),
):
    """列出受管项目根目录。"""
    _emit_roots(_workflow_roots_path(roots_file), json_output)


@workflow_manage_app.command("remove")
def workflow_manage_remove(
    root: Path = typer.Argument(..., help="Managed workspace root"),
    roots_file: Optional[Path] = typer.Option(None, "--roots-file", help="Managed roots JSON path"),
    json_output: bool = typer.Option(False, "--json", help="JSON 输出"),
):
    """移除受管项目根目录。"""
    path = _workflow_roots_path(roots_file)
    canonical = str(root.resolve())
    roots = [existing for existing in _load_workflow_roots(path) if existing != canonical]
    _save_workflow_roots(path, roots)
    _emit_roots(path, json_output)


@app.callback(invoke_without_command=True)
def callback(
    ctx: typer.Context,
    model: Optional[str] = typer.Option(None, "--model", help="使用的模型（不指定则用 provider 默认值）"),
    provider: str = typer.Option(
        os.environ.get("ASTERWYND_PROVIDER", "openai"), "--provider", help="LLM 提供商: openai / anthropic"
    ),
    max_iterations: int = typer.Option(20, "--max-iterations", help="最大迭代次数"),
    system: Optional[str] = typer.Option(None, "--system", help="系统提示"),
    mode: Optional[str] = typer.Option(None, "--mode", help="Agent mode: build / read_only / plan"),
    config_path: Optional[Path] = typer.Option(None, "--config", help="asterwynd.yaml 配置文件路径"),
    banner: bool = typer.Option(True, "--banner/--no-banner", help="交互模式是否显示启动 wordmark"),
):
    """Asterwynd — 轻量级 AI Coding Agent"""
    _setup_logging()
    if ctx.invoked_subcommand is not None:
        return
    config = _load_cli_config(config_path, mode=mode)
    normalized_mode = config.agent.default_mode.value
    run_interactive(
        model,
        provider,
        max_iterations,
        system,
        initial_prompt=None,
        mode=normalized_mode,
        config=config,
        banner=banner,
    )


@app.command()
def run(
    prompt: str = typer.Argument(..., help="要发送给 agent 的提示"),
    model: Optional[str] = typer.Option(None, "--model", help="使用的模型（不指定则用 provider 默认值）"),
    provider: str = typer.Option(
        os.environ.get("ASTERWYND_PROVIDER", "openai"), "--provider", help="LLM 提供商: openai / anthropic"
    ),
    max_iterations: int = typer.Option(20, "--max-iterations", help="最大迭代次数"),
    system: Optional[str] = typer.Option(None, "--system", help="系统提示"),
    mode: Optional[str] = typer.Option(None, "--mode", help="Agent mode: build / read_only / plan"),
    config_path: Optional[Path] = typer.Option(None, "--config", help="asterwynd.yaml 配置文件路径"),
    resume: Optional[str] = typer.Option(None, "--resume", help="从指定 session_id 恢复会话"),
):
    """单轮执行 Agent"""
    _setup_logging()
    config = _load_cli_config(config_path, mode=mode)
    normalized_mode = config.agent.default_mode.value
    resume_snapshot = _load_resume_snapshot(resume, config) if resume else None
    run_single(prompt, model, provider, max_iterations, system, normalized_mode, config, resume_snapshot)


def run_single(
    prompt: str,
    model: Optional[str],
    provider: str,
    max_iterations: int,
    system: Optional[str],
    mode: str = "build",
    config: AsterwyndConfig | None = None,
    resume_snapshot: SessionSnapshot | None = None,
):
    session_id = resume_snapshot.session_id if resume_snapshot else new_session_id()
    run_id = new_run_id()

    messages: list[Message] = []
    messages.append(Message(role="user", content=prompt))

    async def _run():
        if config and config.mcp.servers:
            agent = await build_agent_async(model, provider, mode, config=config)
        else:
            agent = build_agent(model, provider, mode, config=config)
        agent.max_iterations = max_iterations
        if system:
            agent._user_system_prompt = system
        typer.echo(f"Session ID: {session_id}")
        typer.echo(f"Run ID: {run_id}")
        if resume_snapshot:
            typer.echo(f"Resuming session: {session_id}")
        stream_state = {"streamed": False}
        result = await _run_agent_with_cli_streaming(
            agent,
            messages,
            stream_state,
            session_id=session_id,
            run_id=run_id,
            resume_snapshot=resume_snapshot,
        )
        _print_plan_document(agent)
        if not stream_state["streamed"]:
            typer.echo(f"\n【Agent】\n{result.content}")
        if result.tool_calls_made:
            typer.echo(f"\n【工具调用】{len(result.tool_calls_made)} 次")
            _print_tool_call_summaries(result, config)
        mcp_manager = getattr(agent, "mcp_manager", None)
        if mcp_manager is not None:
            await mcp_manager.aclose()
        return result

    asyncio.run(_run())


def run_interactive(
    model: Optional[str],
    provider: str,
    max_iterations: int,
    system: Optional[str],
    initial_prompt: Optional[str] = None,
    mode: str = "build",
    config: AsterwyndConfig | None = None,
    banner: bool = True,
    resume_snapshot: SessionSnapshot | None = None,
):
    session_id = resume_snapshot.session_id if resume_snapshot else new_session_id()

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    if config and config.mcp.servers:
        agent = loop.run_until_complete(build_agent_async(model, provider, mode, config=config))
    else:
        agent = build_agent(model, provider, mode, config=config)
    agent.approval_handler = CliApprovalHandler(interactive=True)
    resolved_model = getattr(agent.llm, "model", model or "default")

    if banner:
        typer.echo(render_tui_banner())
        typer.echo("")
    if resume_snapshot:
        typer.echo(f"{BRAND_NAME} 交互模式 - 已恢复会话 (输入 exit 退出)")
    else:
        typer.echo(f"{BRAND_NAME} 交互模式 (输入 exit 退出)")
    typer.echo(f"模型: {resolved_model} | 提供商: {provider} | Mode: {mode}\n")
    typer.echo(f"Session ID: {session_id}\n")
    agent.max_iterations = max_iterations
    if system:
        agent._user_system_prompt = system
    command_registry = build_default_slash_command_registry(
        getattr(agent, "skill_runtime", None)
    )

    messages: list[Message] = []

    stop_requested = False
    _resume_consumed = False

    async def _run_async():
        nonlocal _resume_consumed
        run_id = new_run_id()
        typer.echo(f"Run ID: {run_id}")
        stream_state = {"streamed": False}
        snap = None if _resume_consumed else resume_snapshot
        _resume_consumed = True
        result = await _run_agent_with_cli_streaming(
            agent,
            messages,
            stream_state,
            session_id=session_id,
            run_id=run_id,
            resume_snapshot=snap,
        )
        return result, stream_state

    def _handle_interactive_command(user_input: str) -> bool:
        nonlocal stop_requested
        command_context = CommandContext(
            agent=agent,
            messages=messages,
            session_id=session_id,
            provider=provider,
            model=str(resolved_model),
        )
        result = loop.run_until_complete(
            command_registry.try_execute(user_input, command_context)
        )
        if result is None:
            return False
        if result.message:
            typer.echo(result.message)
        if not result.continue_session:
            stop_requested = True
        if result.metadata.get("run_agent"):
            skill_runtime = getattr(agent, "skill_runtime", None)
            skill_name = result.metadata.get("skill_name")
            if skill_runtime is not None and skill_name:
                skill_runtime.queue_activation(
                    str(skill_name),
                    source=str(result.metadata.get("activation_source", "slash_command")),
                )
            agent_input = str(result.metadata.get("agent_input") or "").strip()
            if not agent_input:
                agent_input = user_input
            messages.append(Message(role="user", content=agent_input))
            run_result, stream_state = loop.run_until_complete(_run_async())
            _print_plan_document(agent)
            if not stream_state["streamed"]:
                typer.echo(f"\n【Agent】\n{run_result.content}\n")
            _print_tool_call_summaries(run_result, config)
        return True

    try:
        # 如果有初始 prompt，先跑一轮
        if initial_prompt:
            handled_initial = _handle_interactive_command(initial_prompt)
            if not handled_initial:
                messages.append(Message(role="user", content=initial_prompt))
                result, stream_state = loop.run_until_complete(_run_async())
                _print_plan_document(agent)
                if not stream_state["streamed"]:
                    typer.echo(f"\n【Agent】\n{result.content}\n")
                _print_tool_call_summaries(result, config)
            if stop_requested:
                return

        while True:
            try:
                user_input = input("【你】 ")
            except (KeyboardInterrupt, EOFError):
                typer.echo("\n再见！")
                break

            if user_input.strip().lower() in ("exit", "quit", "q"):
                typer.echo("再见！")
                break

            if _handle_interactive_command(user_input):
                if stop_requested:
                    break
                continue

            messages.append(Message(role="user", content=user_input))
            result, stream_state = loop.run_until_complete(_run_async())
            _print_plan_document(agent)
            if not stream_state["streamed"]:
                typer.echo(f"\n【Agent】\n{result.content}\n")
            _print_tool_call_summaries(result, config)
    finally:
        mcp_manager = getattr(agent, "mcp_manager", None)
        if mcp_manager is not None:
            loop.run_until_complete(mcp_manager.aclose())
        loop.close()


async def _run_agent_with_cli_streaming(
    agent: AgentLoop,
    messages: list[Message],
    stream_state: dict,
    *,
    session_id: str,
    run_id: str,
    resume_snapshot: SessionSnapshot | None = None,
):
    async def on_event(event_type: str, data: dict):
        if event_type == "assistant_delta":
            delta = data.get("delta")
            if delta:
                stream_state["streamed"] = True
                typer.echo(delta, nl=False)
        elif event_type == "assistant_stream_complete" and stream_state.get("streamed"):
            typer.echo("")
        elif event_type == "approval_request":
            typer.echo("\n【Approval Required】", err=True)
        elif event_type == "approval_response":
            status = data.get("status", "")
            typer.echo(f"【Approval】{status}", err=True)

    if "on_event" not in inspect.signature(agent.run).parameters:
        return await agent.run(messages, session_id=session_id, run_id=run_id)

    kwargs = dict(
        messages=messages,
        on_event=on_event,
        session_id=session_id,
        run_id=run_id,
    )
    if resume_snapshot is not None:
        kwargs["resume_snapshot"] = resume_snapshot
    return await agent.run(**kwargs)


def _print_plan_document(agent: AgentLoop) -> None:
    document = getattr(agent, "plan_document", None)
    if not isinstance(document, dict):
        return
    markdown = document.get("markdown")
    if not isinstance(markdown, str) or not markdown:
        return
    typer.echo(f"\n【Plan Document】\n{markdown}")


def _print_tool_call_summaries(result, config: AsterwyndConfig | None = None) -> None:
    if not result.tool_calls_made:
        return
    display_config = (config or AsterwyndConfig()).tools.display
    for index, tool_call in enumerate(result.tool_calls_made, start=1):
        tool_result = tool_call.result or ""
        summary = summarize_tool_result(tool_call.name, tool_result, display_config)
        header = f"{index}. {tool_call.name} ({summary.char_count} 字符, {summary.line_count} 行)"
        if summary.collapsed:
            typer.echo(f"\n{header} 摘要:")
            typer.echo(summary.preview)
            typer.echo("完整结果保留在本次运行的工具结果中；需要展开查看请使用 Web UI 或 benchmark trace。")
        else:
            typer.echo(f"\n{header}:")
            typer.echo(tool_result)


@app.command()
def web(
    port: int = typer.Option(8000, "--port", "-p", help="HTTP 端口"),
    host: str = typer.Option("0.0.0.0", "--host", help="绑定地址"),
    provider: str = typer.Option(
        os.environ.get("ASTERWYND_PROVIDER", "openai"), "--provider", help="LLM 提供商: openai / anthropic"
    ),
    model: Optional[str] = typer.Option(None, "--model", help="使用的模型"),
    mode: Optional[str] = typer.Option(None, "--mode", help="Agent mode: build / read_only / plan"),
    config_path: Optional[Path] = typer.Option(None, "--config", help="asterwynd.yaml 配置文件路径"),
    resume: Optional[str] = typer.Option(None, "--resume", help="从指定 session_id 恢复会话"),
):
    """启动 Web UI 服务"""
    _setup_logging()
    import uvicorn
    from web.server import create_app
    from web.debug_hook import debug_enabled

    config = _load_cli_config(config_path, mode=mode)
    normalized_mode = config.agent.default_mode.value
    debug_status = "enabled" if debug_enabled() else "disabled"
    display_host = "127.0.0.1" if host == "0.0.0.0" else host

    if resume:
        resume_snapshot = _load_resume_snapshot(resume, config)
        if resume_snapshot:
            normalized_mode = resume_snapshot.mode.value
            typer.echo(f"Resuming session: {resume}")

    llm = build_llm(provider, model)
    typer.echo(f"{BRAND_NAME} Web UI  →  http://{display_host}:{port}")
    typer.echo(f"Provider: {provider} | Model: {llm.model}")
    typer.echo(f"Mode: {normalized_mode}")
    typer.echo(f"Debug mode: {debug_status}")
    app = create_app(llm, mode=normalized_mode, config=config, resume=resume)
    uvicorn.run(app, host=host, port=port, log_level="info")


@app.command()
def benchmark(
    tasks_dir: Path = typer.Argument(..., help="包含 benchmark task 子目录的目录"),
    agent: str = typer.Option("fake", "--agent", help="Runner: fake / shell / asterwynd / claude"),
    source_repo: Path = typer.Option(Path("."), "--source-repo", help="被测 git repo"),
    runs_dir: Path = typer.Option(Path("benchmarks/runs"), "--runs-dir", help="benchmark 输出目录"),
    provider: str = typer.Option(
        os.environ.get("ASTERWYND_PROVIDER", "openai"), "--provider", help="Asterwynd LLM provider"
    ),
    model: Optional[str] = typer.Option(None, "--model", help="Asterwynd 模型"),
    max_iterations: int = typer.Option(20, "--max-iterations", help="Asterwynd 最大迭代次数"),
    mode: Optional[str] = typer.Option(None, "--mode", help="Agent mode: build / read_only / plan"),
    config_path: Optional[Path] = typer.Option(None, "--config", help="asterwynd.yaml 配置文件路径"),
    parallel: Optional[int] = typer.Option(None, "--parallel", help="benchmark 并发任务数"),
    timeout_seconds: Optional[int] = typer.Option(None, "--timeout-seconds", help="外部 agent 超时时间"),
    shell_command: Optional[str] = typer.Option(None, "--shell-command", help="shell runner 命令"),
    fake_edit_file: Optional[str] = typer.Option(None, "--fake-edit-file", help="fake runner 修改文件"),
    fake_old_string: Optional[str] = typer.Option(None, "--fake-old-string", help="fake runner old string"),
    fake_new_string: Optional[str] = typer.Option(None, "--fake-new-string", help="fake runner new string"),
    keep_worktrees: bool = typer.Option(False, "--keep-worktrees", help="保留任务 worktree 便于调试"),
    clone_cache_dir: Optional[Path] = typer.Option(None, "--clone-cache-dir", help="外部仓库裸克隆缓存目录"),
):
    """运行本地 Coding Agent benchmark"""
    _setup_logging()
    from benchmarks.agent_runner import ClaudeCodeRunner, FakeAgentRunner, AsterwyndRunner, ShellCommandRunner
    from benchmarks.runner import BenchmarkRunner

    config = _load_cli_config(
        config_path,
        mode=mode,
        benchmark_parallel=parallel,
        benchmark_timeout_seconds=timeout_seconds,
    )
    normalized_mode = config.agent.default_mode.value
    if agent == "fake":
        runner_impl = FakeAgentRunner(
            edit_file=fake_edit_file,
            old_string=fake_old_string,
            new_string=fake_new_string,
        )
    elif agent == "shell":
        if not shell_command:
            typer.echo("Error: --shell-command is required for --agent shell", err=True)
            raise SystemExit(1)
        runner_impl = ShellCommandRunner(shell_command)
    elif agent == "claude":
        runner_impl = ClaudeCodeRunner(timeout_seconds=config.benchmark.timeout_seconds)
    elif agent == "asterwynd":
        llm = build_llm(provider, model)
        runner_impl = AsterwyndRunner(
            llm=llm,
            model=getattr(llm, "model", model or ""),
            max_iterations=max_iterations,
            mode=normalized_mode,
            config=config,
            timeout_seconds=config.benchmark.timeout_seconds,
        )
    else:
        typer.echo("Error: --agent must be fake, shell, asterwynd, or claude", err=True)
        raise SystemExit(1)

    runner = BenchmarkRunner(
        agent_runner=runner_impl,
        source_repo=source_repo,
        runs_dir=runs_dir,
        agent_name=agent,
        model=model or "",
        mode=normalized_mode,
        parallel=config.benchmark.parallel,
        keep_worktrees=keep_worktrees,
        clone_cache_dir=clone_cache_dir,
    )
    metadata = asyncio.run(runner.run_all(tasks_dir))
    run_path = runs_dir / metadata.run_id
    typer.echo(f"Benchmark run: {run_path}")
    typer.echo(
        f"Tasks: {metadata.task_count} | passed: {metadata.passed} | "
        f"warnings: {metadata.warnings} | unsupported: {metadata.unsupported} | failed: {metadata.failed}"
    )


session_app = typer.Typer(help="会话管理")
app.add_typer(session_app, name="session")


def _get_session_store(config: AsterwyndConfig | None = None) -> SessionStore:
    return SessionStore(sessions_root=_sessions_root(Path.cwd()))


@session_app.command("list")
def session_list(
    json_output: bool = typer.Option(False, "--json", help="以 JSON 格式输出"),
    config_path: Optional[Path] = typer.Option(None, "--config", help="asterwynd.yaml 配置文件路径"),
):
    """列出可恢复的会话"""
    _setup_logging()
    _load_cli_config(config_path)  # ensure config loaded
    store = _get_session_store()
    sessions = store.list_sessions()

    if not sessions:
        typer.echo("(no saved sessions)")
        return

    if json_output:
        import json
        typer.echo(json.dumps(sessions, ensure_ascii=False, indent=2))
        return

    # Table format
    header = f"{'SESSION_ID':<14} {'CREATED':<21} {'UPDATED':<21} {'MESSAGES':>8} {'MODE':<12}"
    typer.echo(header)
    typer.echo("-" * len(header))
    for s in sessions:
        sid = s["session_id"][:12]
        created = s.get("created_at", "")[:19]
        updated = s.get("updated_at", "")[:19]
        msg_count = s.get("messages", 0)
        mode = s.get("mode", "")
        typer.echo(f"{sid:<14} {created:<21} {updated:<21} {msg_count:>8} {mode:<12}")


@session_app.command("resume")
def session_resume(
    session_id: str = typer.Argument(..., help="要恢复的会话 ID"),
    model: Optional[str] = typer.Option(None, "--model", help="使用的模型"),
    provider: str = typer.Option(
        os.environ.get("ASTERWYND_PROVIDER", "openai"), "--provider", help="LLM 提供商"
    ),
    max_iterations: int = typer.Option(20, "--max-iterations", help="最大迭代次数"),
    system: Optional[str] = typer.Option(None, "--system", help="系统提示"),
    mode: Optional[str] = typer.Option(None, "--mode", help="Agent mode: build / read_only / plan"),
    config_path: Optional[Path] = typer.Option(None, "--config", help="asterwynd.yaml 配置文件路径"),
):
    """恢复会话并进入交互模式"""
    _setup_logging()
    config = _load_cli_config(config_path, mode=mode)
    normalized_mode = config.agent.default_mode.value

    snapshot = _load_resume_snapshot(session_id, config)
    if snapshot is None:
        return

    typer.echo(f"Resuming session: {session_id}")
    typer.echo(f"  Mode: {snapshot.mode.value}")
    typer.echo(f"  Messages: {len(snapshot.messages)}")
    typer.echo(f"  Created: {snapshot.created_at[:19]}")
    typer.echo("")

    run_interactive(
        model,
        provider,
        max_iterations,
        system,
        initial_prompt=None,
        mode=normalized_mode,
        config=config,
        banner=False,
        resume_snapshot=snapshot,
    )


@session_app.command("rm")
def session_rm(
    session_id: str = typer.Argument(..., help="要删除的会话 ID"),
    force: bool = typer.Option(False, "--force", "-f", help="跳过确认直接删除"),
    config_path: Optional[Path] = typer.Option(None, "--config", help="asterwynd.yaml 配置文件路径"),
):
    """删除会话"""
    _setup_logging()
    _load_cli_config(config_path)
    store = _get_session_store()

    if not force:
        typer.echo(f"Are you sure you want to delete session '{session_id}'?")
        confirm = input("Type 'yes' to confirm: ")
        if confirm.strip().lower() != "yes":
            typer.echo("Cancelled.")
            return

    removed = store.remove(session_id)
    if removed:
        typer.echo(f"Session '{session_id}' removed.")
    else:
        typer.echo(f"Error: Session '{session_id}' not found.", err=True)
        raise SystemExit(1)


if __name__ == "__main__":
    app()
