#!/usr/bin/env python3
"""
Asterwynd CLI 入口

用法:
    python cli.py "你好，介绍一下自己"
    python cli.py --provider anthropic --model claude-sonnet-4-20250514 "你好"
    python cli.py --interactive --provider anthropic
"""
import asyncio
import inspect
import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
import typer

# 自动加载 .env 文件（如果存在）
load_dotenv(Path(__file__).parent / ".env")

from agent.approval import ApprovalHandler, CliApprovalHandler
from agent.loop import AgentLoop
from agent.commands import CommandContext, build_default_slash_command_registry
from agent.config import ConfigError, ConfigOverrides, AsterwyndConfig, load_config
from agent.message import Message, system_message
from agent.openai_llm import OpenAILLM
from agent.anthropic_llm import AnthropicLLM
from agent.run_config import AgentMode, AgentRunConfig, ModePolicy, parse_agent_mode
from agent.subagent.manager import SubAgentManager
from agent.tools.factory import build_default_tool_registry
from agent.workspace_policy import WorkspacePolicy
from agent.hooks.manager import HookManager
from agent.hooks.builtin import LoggingHook, TracingHook
from agent.memory.manager import MemoryManager
from agent.llm import LLM
from agent.run_identity import new_run_id, new_session_id
from agent.skills import SkillRuntime
from agent.tool_result_display import summarize_tool_result
from agent.branding import BRAND_NAME, render_tui_banner

LOG_DIR = Path(__file__).parent / "logs"
LOG_DIR.mkdir(exist_ok=True)
LOG_FILE = LOG_DIR / f"asterwynd-{__import__('datetime').datetime.now().strftime('%Y%m%d-%H%M%S')}.log"

_LOG_LEVEL = getattr(logging, os.environ.get("ASTERWYND_LOG_LEVEL", "INFO").upper(), logging.INFO)

logging.basicConfig(
    level=_LOG_LEVEL,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
    handlers=[
        logging.StreamHandler(),
        RotatingFileHandler(LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=5, encoding="utf-8"),
    ],
)
logger = logging.getLogger("asterwynd.cli")

app = typer.Typer()

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
    config = config or AsterwyndConfig()
    llm = build_llm(provider, model)
    run_config = AgentRunConfig(mode=parse_agent_mode(_normalize_user_mode(mode)))
    workspace_policy = WorkspacePolicy(
        command_denylist=config.tools.command_denylist,
    )
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

    return AgentLoop(
        llm=llm,
        tool_registry=registry,
        hooks=hooks,
        memory=memory,
        subagent_manager=subagent_manager,
        expose_subagent_tools=True,
        run_config=run_config,
        tool_result_display=config.tools.display,
        skill_runtime=skill_runtime,
        approval_handler=approval_handler,
    )

@app.command()
def main(
    prompt: Optional[str] = typer.Argument(None, help="要发送给 agent 的提示（交互模式下可选）"),
    model: Optional[str] = typer.Option(None, "--model", help="使用的模型（不指定则用 provider 默认值）"),
    provider: str = typer.Option(
        os.environ.get("ASTERWYND_PROVIDER", "openai"), "--provider", help="LLM 提供商: openai / anthropic"
    ),
    max_iterations: int = typer.Option(20, "--max-iterations", help="最大迭代次数"),
    system: Optional[str] = typer.Option(None, "--system", help="系统提示"),
    interactive: bool = typer.Option(False, "--interactive", "-i", help="交互模式"),
    mode: Optional[str] = typer.Option(None, "--mode", help="Agent mode: build / read_only / plan"),
    config_path: Optional[Path] = typer.Option(None, "--config", help="asterwynd.yaml 配置文件路径"),
    banner: bool = typer.Option(True, "--banner/--no-banner", help="交互模式是否显示启动 wordmark"),
):
    config = _load_cli_config(config_path, mode=mode)
    normalized_mode = config.agent.default_mode.value
    if interactive:
        run_interactive(
            model,
            provider,
            max_iterations,
            system,
            prompt,
            normalized_mode,
            config,
            banner=banner,
        )
    else:
        if not prompt:
            typer.echo("Error: PROMPT is required in single-prompt mode", err=True)
            raise SystemExit(1)
        run_single(prompt, model, provider, max_iterations, system, normalized_mode, config)

def run_single(
    prompt: str,
    model: Optional[str],
    provider: str,
    max_iterations: int,
    system: Optional[str],
    mode: str = "build",
    config: AsterwyndConfig | None = None,
):
    agent = build_agent(model, provider, mode, config=config)
    agent.max_iterations = max_iterations
    session_id = new_session_id()
    run_id = new_run_id()

    messages: list[Message] = []
    if system:
        messages.append(system_message(system))

    system_prompt = (
        "你是一个有用、诚实的人工智能助手。"
        "你可以调用工具来完成任务。"
    )
    messages.append(system_message(system_prompt))
    messages.append(Message(role="user", content=prompt))

    async def _run():
        typer.echo(f"Session ID: {session_id}")
        typer.echo(f"Run ID: {run_id}")
        stream_state = {"streamed": False}
        result = await _run_agent_with_cli_streaming(
            agent,
            messages,
            stream_state,
            session_id=session_id,
            run_id=run_id,
        )
        _print_plan_document(agent)
        if not stream_state["streamed"]:
            typer.echo(f"\n【Agent】\n{result.content}")
        if result.tool_calls_made:
            typer.echo(f"\n【工具调用】{len(result.tool_calls_made)} 次")
            _print_tool_call_summaries(result, config)
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
):
    agent = build_agent(model, provider, mode, config=config)
    agent.approval_handler = CliApprovalHandler(interactive=True)
    resolved_model = getattr(agent.llm, "model", model or "default")
    session_id = new_session_id()

    if banner:
        typer.echo(render_tui_banner())
        typer.echo("")
    typer.echo(f"{BRAND_NAME} 交互模式 (输入 exit 退出)")
    typer.echo(f"模型: {resolved_model} | 提供商: {provider} | Mode: {mode}\n")
    typer.echo(f"Session ID: {session_id}\n")
    agent.max_iterations = max_iterations
    command_registry = build_default_slash_command_registry(
        getattr(agent, "skill_runtime", None)
    )

    messages: list[Message] = []
    system_prompt = (
        "你是一个有用、诚实的人工智能助手。"
        "你可以调用工具来完成任务。"
    )
    messages.append(system_message(system_prompt))
    if system:
        messages.append(system_message(system))

    # 复用持久 event loop，避免 httpx.AsyncClient 连接池引用已关闭的 loop
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    stop_requested = False

    async def _run_async():
        run_id = new_run_id()
        typer.echo(f"Run ID: {run_id}")
        stream_state = {"streamed": False}
        result = await _run_agent_with_cli_streaming(
            agent,
            messages,
            stream_state,
            session_id=session_id,
            run_id=run_id,
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
        loop.close()


async def _run_agent_with_cli_streaming(
    agent: AgentLoop,
    messages: list[Message],
    stream_state: dict,
    *,
    session_id: str,
    run_id: str,
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

    return await agent.run(
        messages,
        on_event=on_event,
        session_id=session_id,
        run_id=run_id,
    )


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
):
    """启动 Web UI 服务"""
    import uvicorn
    from web.server import create_app
    from web.debug_hook import debug_enabled

    config = _load_cli_config(config_path, mode=mode)
    normalized_mode = config.agent.default_mode.value
    debug_status = "enabled" if debug_enabled() else "disabled"
    display_host = "127.0.0.1" if host == "0.0.0.0" else host

    llm = build_llm(provider, model)
    typer.echo(f"{BRAND_NAME} Web UI  →  http://{display_host}:{port}")
    typer.echo(f"Provider: {provider} | Model: {llm.model}")
    typer.echo(f"Mode: {normalized_mode}")
    typer.echo(f"Debug mode: {debug_status}")
    app = create_app(llm, mode=normalized_mode, config=config)
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
    """运行本地 Coding Agent benchmark。"""
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


if __name__ == "__main__":
    app()
