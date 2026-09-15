"""Workflow 记录的落盘与读取（change ``benchmark-workflow-replay``，D1/D2）。

三种 benchmark 运行模式共享本模块：

- ``template``：固定 Pattern 模板当被测编排，不落盘记录；
- ``dynamic-record``：模型自由生成 workflow，执行的同时**旁路采集**规范化记录；
- ``dynamic-replay``：读已保存的记录，**不重跑规划模型**，离线重放 spec。

落盘 schema（grill Q1 写法 B）：**一任务一份文件**，顶层是 ``workflows`` 列表
而不是单个 spec——一个任务可能起 0 张、1 张或多张图（``manager.list_workflows()``
返回列表），单对象 schema 会把第二张图覆盖掉。

采集**只记真正 ``run()`` 过的图**：``DeclareWorkflow`` 只注册不执行
（``agent/tools/builtin/subagents.py``），未启动的 ``declared`` 态图不进列表——
否则 replay 会重放出 record 时并不存在的行为。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from agent.subagent.workflow import SCHEMA_VERSION

#: 采集状态（三态 + replay 侧缺文件）。
COLLECTION_STATUS_OK = "ok"
COLLECTION_STATUS_NO_WORKFLOW = "no_workflow"
COLLECTION_STATUS_FAILED = "failed"
#: replay 侧：本任务没有可读的记录（不是采集失败，是 record 那轮压根没写）。
COLLECTION_STATUS_MISSING = "missing"

WORKFLOW_RECORD_FILENAME = "workflow_record.json"

#: 记录里每张图的规范字段（D2）。``spec`` 是 ``WorkflowSpec.to_dict()``，
#: replay 时 ``parse_workflow_spec`` 可完整还原（含 foreach 的 ``items`` 与 route
#: 的 ``$ref``）；``scheduler_version`` 是 spec 方言版本，跨版本 replay 的锚点。
RECORD_FIELDS: tuple[str, ...] = (
    "workflow_id",
    "workflow_spec_hash",
    "scheduler_version",
    "spec",
    "budget_config",
    "seed",
    "model",
    "temperature",
    #: record 那次跑**实测**到的编排指标（D6/Q6 可比性断言的对照面）：
    #: 没有它，replay 就没有东西可比——Q6 要求的 fake 全等断言
    #: （spec_hash/node_count/run_count/status）无从判定。它不进 replay 的输入面
    #: （replay 只读 ``spec``），纯观测记录。
    "observed",
)

#: ``observed`` 里参与可比性断言的键（Q6）。
OBSERVED_FIELDS: tuple[str, ...] = (
    "node_count",
    "run_count",
    "status",
)


def _started(scheduler: Any) -> bool:
    """该调度器是否真的 ``run()`` 过（``declared`` 态只注册不执行）。"""
    if getattr(scheduler, "started", False):
        return True
    status_fn = getattr(scheduler, "status", None)
    if not callable(status_fn):
        return False
    try:
        return status_fn().get("status") != "declared"
    except Exception:  # noqa: BLE001 - 采集是尽力而为，不能拖垮 run
        return False


def _budget_config_dict(scheduler: Any) -> dict[str, Any]:
    """该 workflow 的四维度预算配置（C4 的 ``WorkflowBudgetConfig``）。"""
    manager = getattr(scheduler, "manager", None)
    config = getattr(manager, "config", None)
    workflow = getattr(getattr(config, "subagents", None), "workflow", None)
    budget = getattr(workflow, "budget", None)
    if budget is None:
        return {}
    return {
        "max_total_tokens": getattr(budget, "max_total_tokens", None),
        "max_total_cost_usd": getattr(budget, "max_total_cost_usd", None),
        "max_total_runs": getattr(budget, "max_total_runs", None),
        "max_wall_time_s": getattr(budget, "max_wall_time_s", None),
    }


def _observed_metrics(scheduler: Any) -> dict[str, Any]:
    """该次运行的实测编排指标（Q6 可比性断言的对照面）。"""
    try:
        envelope = scheduler.status()
    except Exception:  # noqa: BLE001 - 观测缺失不该让整条记录采集失败
        return {}
    return {
        "node_count": len(envelope.get("nodes") or []),
        "run_count": envelope.get("run_count"),
        "status": envelope.get("status"),
        # 只报不判的字段（Q6）：wall-clock/token 噪声大，留作人工比对。
        "peak_active": envelope.get("peak_active"),
        "critical_path_s": envelope.get("critical_path_s"),
        "cost_usd": envelope.get("total_cost"),
    }


def workflow_record_entry(
    scheduler: Any,
    *,
    model: str | None = None,
    temperature: float | None = None,
    seed: int | None = None,
) -> dict[str, Any]:
    """把一张已运行的调度器规范化成一条记录（spec + hash + 元数据）。"""
    spec = scheduler.spec
    return {
        "workflow_id": getattr(scheduler, "workflow_id", None),
        "workflow_spec_hash": spec.spec_hash,
        "scheduler_version": SCHEMA_VERSION,
        "spec": spec.to_dict(),
        "budget_config": _budget_config_dict(scheduler),
        "seed": seed,
        "model": model,
        "temperature": temperature,
        "observed": _observed_metrics(scheduler),
    }


def collect_workflow_records(
    manager: Any,
    *,
    model: str | None = None,
    temperature: float | None = None,
    seed: int | None = None,
) -> tuple[list[dict], str, str | None]:
    """旁路采集本次 run 起过的全部 workflow。

    返回 ``(records, collection_status, collection_error)``：

    - 没有任何图跑过 → ``no_workflow`` + 空列表；
    - 有图且全部采集成功 → ``ok``；
    - 采集途中异常 → ``failed`` + 错误文本 + **已采到的部分列表**（不静默丢）。

    采集顺序 = ``manager.list_workflows()`` 的注册顺序（dict 插入序），replay 按序
    重放全部。采集失败**不影响** run 完成。
    """
    records: list[dict] = []
    for workflow_id in manager.list_workflows():
        scheduler = manager.get_workflow(workflow_id)
        if scheduler is None or not _started(scheduler):
            continue
        try:
            records.append(
                workflow_record_entry(
                    scheduler,
                    model=model,
                    temperature=temperature,
                    seed=seed,
                )
            )
        except Exception as exc:  # noqa: BLE001 - 采集失败降级为 failed，不抛出
            return records, COLLECTION_STATUS_FAILED, f"{type(exc).__name__}: {exc}"
    if not records:
        return [], COLLECTION_STATUS_NO_WORKFLOW, None
    return records, COLLECTION_STATUS_OK, None


def record_path(task_output: str | Path) -> Path:
    """一任务的记录路径 = ``<task_output>/workflow_record.json``。

    record 侧写它、replay 侧按同一个路径读——``--workflow-record <run-dir>``
    只是「从哪个 run 目录取」，文件名由本函数唯一确定。
    """
    return Path(task_output) / WORKFLOW_RECORD_FILENAME


def write_workflow_record(task_output: str | Path, record: dict) -> Path:
    """落盘一份任务级记录（尽力而为：失败不打断 run）。"""
    path = record_path(task_output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(record, indent=2, ensure_ascii=False) + "\n",
        errors="replace",
    )
    return path


def read_workflow_record(task_output: str | Path) -> dict | None:
    """读一份任务级记录；文件缺失或损坏返回 ``None``。"""
    path = record_path(task_output)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return None


def build_record(
    *,
    workflow_mode: str,
    records: list[dict],
    collection_status: str,
    collection_error: str | None = None,
) -> dict:
    """组装顶层记录（Q1 写法 B：``workflows`` 列表 + ``collection_status``）。"""
    payload: dict[str, Any] = {
        "workflow_mode": workflow_mode,
        "collection_status": collection_status,
        "workflows": list(records),
    }
    if collection_error:
        payload["collection_error"] = collection_error
    return payload
