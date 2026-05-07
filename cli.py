#!/usr/bin/env python3
"""
MyAgent CLI 入口

用法:
    python cli.py --model gpt-4 "你好，介绍一下自己"
    python cli.py --model gpt-4o-mini --interactive
"""
import asyncio
import logging
import os
import sys
from typing import Optional

import typer

from agent.loop import AgentLoop
from agent.message import Message, system_message
from agent.openai_llm import OpenAILLM
from agent.tools import get_default_tools, ToolRegistry
from agent.hooks.manager import HookManager
from agent.hooks.builtin import LoggingHook, TracingHook
from agent.memory.manager import MemoryManager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)
logger = logging.getLogger("myagent.cli")

app = typer.Typer()

def build_agent(model: str = "gpt-4o-mini") -> AgentLoop:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        typer.echo("Error: OPENAI_API_KEY not set", err=True)
        raise SystemExit(1)

    llm = OpenAILLM(api_key=api_key)
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
    prompt: str = typer.Argument(..., help="要发送给 agent 的提示"),
    model: str = typer.Option("gpt-4o-mini", "--model", help="使用的模型"),
    max_iterations: int = typer.Option(20, "--max-iterations", help="最大迭代次数"),
    system: Optional[str] = typer.Option(None, "--system", help="系统提示"),
    interactive: bool = typer.Option(False, "--interactive", "-i", help="交互模式"),
):
    if interactive:
        run_interactive(model, max_iterations, system)
    else:
        run_single(prompt, model, max_iterations, system)

def run_single(prompt: str, model: str, max_iterations: int, system: Optional[str]):
    agent = build_agent(model)
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

def run_interactive(model: str, max_iterations: int, system: Optional[str]):
    typer.echo("MyAgent 交互模式 (输入 exit 退出)")
    typer.echo(f"模型: {model}\n")

    agent = build_agent(model)
    agent.max_iterations = max_iterations

    messages: list[Message] = []
    system_prompt = (
        "你是一个有用、诚实的人工智能助手。"
        "你可以调用工具来完成任务。"
    )
    messages.append(system_message(system_prompt))
    if system:
        messages.append(system_message(system))

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

        async def _run():
            return await agent.run(messages)

        result = asyncio.run(_run())
        typer.echo(f"\n【Agent】\n{result.content}\n")
        messages.append(Message(role="assistant", content=result.content))

if __name__ == "__main__":
    app()