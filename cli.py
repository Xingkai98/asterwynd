#!/usr/bin/env python3
"""
MyAgent CLI 入口

用法:
    python cli.py "你好，介绍一下自己"
    python cli.py --provider anthropic --model claude-sonnet-4-20250514 "你好"
    python cli.py --interactive --provider anthropic
"""
import asyncio
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

from agent.loop import AgentLoop
from agent.config import ConfigError, ConfigOverrides, MyAgentConfig, load_config
from agent.message import Message, system_message
from agent.openai_llm import OpenAILLM
from agent.anthropic_llm import AnthropicLLM
from agent.run_config import AgentMode, AgentRunConfig, ModePolicy, parse_agent_mode
from agent.tools.factory import build_default_tool_registry
from agent.workspace_policy import WorkspacePolicy
from agent.hooks.manager import HookManager
from agent.hooks.builtin import LoggingHook, TracingHook
from agent.memory.manager import MemoryManager
from agent.llm import LLM
from agent.run_identity import new_run_id, new_session_id
from agent.tool_result_display import summarize_tool_result

LOG_DIR = Path(__file__).parent / "logs"
LOG_DIR.mkdir(exist_ok=True)
LOG_FILE = LOG_DIR / f"myagent-{__import__('datetime').datetime.now().strftime('%Y%m%d-%H%M%S')}.log"

_LOG_LEVEL = getattr(logging, os.environ.get("MYAGENT_LOG_LEVEL", "INFO").upper(), logging.INFO)

logging.basicConfig(
    level=_LOG_LEVEL,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
    handlers=[
        logging.StreamHandler(),
        RotatingFileHandler(LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=5, encoding="utf-8"),
    ],
)
logger = logging.getLogger("myagent.cli")

app = typer.Typer()

def build_llm(provider: str, model: Optional[str] = None) -> LLM:
    if model is None:
        model = os.environ.get("MYAGENT_MODEL")
    kwargs = {}
    if model is not None:
        kwargs["model"] = model
    if provider == "anthropic":
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            typer.echo("Error: ANTHROPIC_API_KEY not set", err=True)
            raise SystemExit(1)
        base_url = os.environ.get("ANTHROPIC_BASE_URL", "https://api.anthropic.com")
        return AnthropicLLM(api_key=api_key, base_url=base_url, **kwargs)
    else:
        # openai (default)
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            typer.echo("Error: OPENAI_API_KEY not set", err=True)
            raise SystemExit(1)
        base_url = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
        return OpenAILLM(api_key=api_key, base_url=base_url, **kwargs)

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
) -> MyAgentConfig:
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
    config: MyAgentConfig | None = None,
) -> AgentLoop:
    config = config or MyAgentConfig()
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
        ),
        ignore_patterns=config.tools.ignore_patterns,
    )

    hooks = HookManager([
        LoggingHook(verbose=False),
        TracingHook(),
    ])

    memory = MemoryManager(max_tokens=80_000)

    return AgentLoop(
        llm=llm,
        tool_registry=registry,
        hooks=hooks,
        memory=memory,
        run_config=run_config,
        tool_result_display=config.tools.display,
    )

@app.command()
def main(
    prompt: Optional[str] = typer.Argument(None, help="要发送给 agent 的提示（交互模式下可选）"),
    model: Optional[str] = typer.Option(None, "--model", help="使用的模型（不指定则用 provider 默认值）"),
    provider: str = typer.Option(
        os.environ.get("MYAGENT_PROVIDER", "openai"), "--provider", help="LLM 提供商: openai / anthropic"
    ),
    max_iterations: int = typer.Option(20, "--max-iterations", help="最大迭代次数"),
    system: Optional[str] = typer.Option(None, "--system", help="系统提示"),
    interactive: bool = typer.Option(False, "--interactive", "-i", help="交互模式"),
    mode: Optional[str] = typer.Option(None, "--mode", help="Agent mode: build / read_only / plan"),
    config_path: Optional[Path] = typer.Option(None, "--config", help="myagent.yaml 配置文件路径"),
):
    config = _load_cli_config(config_path, mode=mode)
    normalized_mode = config.agent.default_mode.value
    if interactive:
        run_interactive(model, provider, max_iterations, system, prompt, normalized_mode, config)
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
    config: MyAgentConfig | None = None,
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
        result = await agent.run(messages, session_id=session_id, run_id=run_id)
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
    config: MyAgentConfig | None = None,
):
    agent = build_agent(model, provider, mode, config=config)
    resolved_model = getattr(agent.llm, "model", model or "default")
    session_id = new_session_id()

    typer.echo("MyAgent 交互模式 (输入 exit 退出)")
    typer.echo(f"模型: {resolved_model} | 提供商: {provider} | Mode: {mode}\n")
    typer.echo(f"Session ID: {session_id}\n")
    agent.max_iterations = max_iterations

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

    async def _run_async():
        run_id = new_run_id()
        typer.echo(f"Run ID: {run_id}")
        return await agent.run(messages, session_id=session_id, run_id=run_id)

    try:
        # 如果有初始 prompt，先跑一轮
        if initial_prompt:
            messages.append(Message(role="user", content=initial_prompt))
            result = loop.run_until_complete(_run_async())
            typer.echo(f"\n【Agent】\n{result.content}\n")
            _print_tool_call_summaries(result, config)

        while True:
            try:
                user_input = input("【你】 ")
            except (KeyboardInterrupt, EOFError):
                typer.echo("\n再见！")
                break

            if user_input.strip().lower() in ("exit", "quit", "q"):
                typer.echo("再见！")
                break

            messages.append(Message(role="user", content=user_input))
            result = loop.run_until_complete(_run_async())
            typer.echo(f"\n【Agent】\n{result.content}\n")
            _print_tool_call_summaries(result, config)
    finally:
        loop.close()


def _print_tool_call_summaries(result, config: MyAgentConfig | None = None) -> None:
    if not result.tool_calls_made:
        return
    display_config = (config or MyAgentConfig()).tools.display
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
        os.environ.get("MYAGENT_PROVIDER", "openai"), "--provider", help="LLM 提供商: openai / anthropic"
    ),
    model: Optional[str] = typer.Option(None, "--model", help="使用的模型"),
    mode: Optional[str] = typer.Option(None, "--mode", help="Agent mode: build / read_only / plan"),
    config_path: Optional[Path] = typer.Option(None, "--config", help="myagent.yaml 配置文件路径"),
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
    typer.echo(f"MyAgent Web UI  →  http://{display_host}:{port}")
    typer.echo(f"Provider: {provider} | Model: {llm.model}")
    typer.echo(f"Mode: {normalized_mode}")
    typer.echo(f"Debug mode: {debug_status}")
    app = create_app(llm, mode=normalized_mode, config=config)
    uvicorn.run(app, host=host, port=port, log_level="info")


@app.command()
def benchmark(
    tasks_dir: Path = typer.Argument(..., help="包含 benchmark task 子目录的目录"),
    agent: str = typer.Option("fake", "--agent", help="Runner: fake / shell / myagent / claude"),
    source_repo: Path = typer.Option(Path("."), "--source-repo", help="被测 git repo"),
    runs_dir: Path = typer.Option(Path("benchmarks/runs"), "--runs-dir", help="benchmark 输出目录"),
    provider: str = typer.Option(
        os.environ.get("MYAGENT_PROVIDER", "openai"), "--provider", help="MyAgent LLM provider"
    ),
    model: Optional[str] = typer.Option(None, "--model", help="MyAgent 模型"),
    max_iterations: int = typer.Option(20, "--max-iterations", help="MyAgent 最大迭代次数"),
    mode: Optional[str] = typer.Option(None, "--mode", help="Agent mode: build / read_only / plan"),
    config_path: Optional[Path] = typer.Option(None, "--config", help="myagent.yaml 配置文件路径"),
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
    from benchmarks.agent_runner import ClaudeCodeRunner, FakeAgentRunner, MyAgentRunner, ShellCommandRunner
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
    elif agent == "myagent":
        llm = build_llm(provider, model)
        runner_impl = MyAgentRunner(
            llm=llm,
            model=getattr(llm, "model", model or ""),
            max_iterations=max_iterations,
            mode=normalized_mode,
            config=config,
            timeout_seconds=config.benchmark.timeout_seconds,
        )
    else:
        typer.echo("Error: --agent must be fake, shell, myagent, or claude", err=True)
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
        f"warnings: {metadata.warnings} | failed: {metadata.failed}"
    )


if __name__ == "__main__":
    app()
