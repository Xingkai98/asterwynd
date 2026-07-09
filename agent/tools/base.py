# agent/tools/base.py
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any
from agent.llm import ToolCallDelta
from agent.tool_permissions import (
    ToolCapability,
    ToolOrigin,
    ToolPermission,
    ToolRiskLevel,
)


def tool_parameters(
    name: str,
    description: str,
    parameters: dict,
):
    """工具装饰器：附加元信息到 Tool 子类"""
    def decorator(cls):
        # Only set from decorator args if class doesn't already define them with truthy values
        if not getattr(cls, 'name', None):
            cls.name = name
        if not getattr(cls, 'description', None):
            cls.description = description
        if not getattr(cls, 'parameters', None):
            cls.parameters = parameters
        return cls
    return decorator


class Tool(ABC):
    """工具基类"""
    name: str
    description: str
    parameters: dict  # JSON Schema
    read_only: bool = False
    dangerous: bool = False
    parallelizable: bool = False
    allowed_modes: tuple[str, ...] | None = None
    permission: ToolPermission | None = None

    @abstractmethod
    async def execute(self, **kwargs) -> str:
        """执行工具，返回结果字符串"""
        ...

    def get_schema(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }

    def get_permission(self) -> ToolPermission:
        if self.permission is not None:
            return self.permission
        if self.dangerous:
            return ToolPermission(
                capabilities=frozenset({ToolCapability.COMMAND_EXECUTE}),
                risk_level=ToolRiskLevel.HIGH,
                origin=ToolOrigin.BUILTIN,
            )
        if self.read_only:
            return ToolPermission(
                capabilities=frozenset({ToolCapability.WORKSPACE_READ}),
                risk_level=ToolRiskLevel.LOW,
                origin=ToolOrigin.BUILTIN,
            )
        return ToolPermission(
            capabilities=frozenset({ToolCapability.WORKSPACE_WRITE}),
            risk_level=ToolRiskLevel.MEDIUM,
            origin=ToolOrigin.BUILTIN,
        )


@dataclass
class ToolCall:
    """一次工具调用"""
    id: str
    name: str
    arguments: dict

    @classmethod
    def from_delta(cls, delta: "ToolCallDelta", arguments: dict) -> "ToolCall":
        return cls(id=delta.id, name=delta.name, arguments=arguments)
