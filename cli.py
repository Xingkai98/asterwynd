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
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
import typer

# 自动加载 .env 文件（如果存在）
load_dotenv(Path(__file__).parent / ".env")

from agent.loop import AgentLoop
from agent.message import Message, system_message
from agent.openai_llm import OpenAILLM
from agent.anthropic_llm import AnthropicLLM
from agent.tools import get_default_tools, ToolRegistry
from agent.hooks.manager import HookManager
from agent.hooks.builtin import LoggingHook, TracingHook
from agent.memory.manager import MemoryManager
from agent.llm import LLM

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)
logger = logging.getLogger("myagent.cli")

app = typer.Typer()

def build_llm(provider: str, model: str) -> LLM:
    if provider == "anthropic":
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            typer.echo("Error: ANTHROPIC_API_KEY not set", err=True)
            raise SystemExit(1)
        base_url = os.environ.get("ANTHROPIC_BASE_URL", "https://api.anthropic.com")
        return AnthropicLLM(api_key=api_key, base_url=base_url, model=model)
    else:
        # openai (default)
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            typer.echo("Error: OPENAI_API_KEY not set", err=True)
            raise SystemExit(1)
        base_url = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
        return OpenAILLM(api_key=api_key, base_url=base_url, model=model)

def build_agent(model: str = "gpt-4o-mini", provider: str = "openai") -> AgentLoop:
    llm = build_llm(provider, model)
    registry = ToolRegistry()
    for tool in get_default_tools():
        registry.register(tool)

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
    )

@app.command()
def main(
    prompt: Optional[str] = typer.Argument(None, help="要发送给 agent 的提示（交互模式下可选）"),
    model: str = typer.Option("gpt-4o-mini", "--model", help="使用的模型"),
    provider: str = typer.Option("openai", "--provider", help="LLM 提供商: openai / anthropic"),
    max_iterations: int = typer.Option(20, "--max-iterations", help="最大迭代次数"),
    system: Optional[str] = typer.Option(None, "--system", help="系统提示"),
    interactive: bool = typer.Option(False, "--interactive", "-i", help="交互模式"),
):
    if interactive:
        run_interactive(model, provider, max_iterations, system, prompt)
    else:
        if not prompt:
            typer.echo("Error: PROMPT is required in single-prompt mode", err=True)
            raise SystemExit(1)
        run_single(prompt, model, provider, max_iterations, system)

def run_single(prompt: str, model: str, provider: str, max_iterations: int, system: Optional[str]):
    agent = build_agent(model, provider)
    agent.max_iterations = max_iterations

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
        result = await agent.run(messages)
        typer.echo(f"\n【Agent】\n{result.content}")
        if result.tool_calls_made:
            typer.echo(f"\n【工具调用】{len(result.tool_calls_made)} 次")
        return result

    asyncio.run(_run())

def run_interactive(model: str, provider: str, max_iterations: int, system: Optional[str], initial_prompt: Optional[str] = None):
    typer.echo("MyAgent 交互模式 (输入 exit 退出)")
    typer.echo(f"模型: {model} | 提供商: {provider}\n")

    agent = build_agent(model, provider)
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
        return await agent.run(messages)

    try:
        # 如果有初始 prompt，先跑一轮
        if initial_prompt:
            messages.append(Message(role="user", content=initial_prompt))
            result = loop.run_until_complete(_run_async())
            typer.echo(f"\n【Agent】\n{result.content}\n")
            messages.append(Message(role="assistant", content=result.content))

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
            messages.append(Message(role="assistant", content=result.content))
    finally:
        loop.close()

if __name__ == "__main__":
    app()