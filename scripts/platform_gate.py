#!/usr/bin/env python3
"""platform-gate：master 分支保护目标状态幂等配置脚本（stdlib-only）。

使用 `gh api` CLI 访问 GitHub branch protection REST API，复用 gh 认证
（本地与 CI runner 预装 gh；不引入 requests/pygithub）。目标状态由
scripts/platform-gate.json 声明（归一化形状：`enabled` 对象形态，人可读、
与 verify 比对同构；`_description` 注释可出现在任意深度）。

子命令：
- --apply   GET-modify-PUT：GET 当前 protection → 用声明字段覆盖（merge）→
            剔除只读派生字段（url/contexts_url/checks/*_url）→ 按 PUT 请求
            形状显式双向变换（`enabled` 对象→布尔、`restrictions: null`、
            递归剥离 `_description`）→ PUT 完整 payload（四必需字段
            enforce_admins / required_pull_request_reviews /
            required_status_checks / restrictions）。apply 前打印「目标 vs
            当前实况」逐字段 diff 供执行者确认（diff 走 stderr），stdout
            只输出结果 JSON；脚本不交互（无 y/n 提示）。
- --verify  只读漂移检测：GET 当前 protection → 白名单归一化比对（只读
            声明字段，忽略 url/contexts_url/checks 等只读派生字段；声明
            字段 null/缺失视为漂移）→ 逐字段 diff 走 stderr，stdout 输出
            {"ok": bool, "diff": {...}}；一致 exit 0，漂移 exit 1。

参数：
- --config <path>   目标状态 JSON 路径（默认 scripts/platform-gate.json）。
- --repo <owner/repo>  覆盖仓库（提供时完全不调用 git remote get-url）。

错误处理 fail-closed：gh 缺失 / 认证失败 / API 错误 / 目标 JSON schema
非法 / git remote 解析失败 → 明确报错并 exit 2，不执行部分写入。
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from typing import Any

DEFAULT_CONFIG = "scripts/platform-gate.json"
MASTER_BRANCH = "master"

# GitHub branch protection API 的只读派生字段：apply 构造 PUT body 时递归剔除。
READONLY_DERIVED_KEYS = frozenset({"url", "contexts_url", "checks"})
READONLY_DERIVED_SUFFIX = "_url"

# 目标 JSON 允许的顶层字段（_description 是注释，剥离后再校验）。
DECLARED_FIELDS = frozenset({
    "required_status_checks",
    "required_conversation_resolution",
    "required_pull_request_reviews",
    "enforce_admins",
})
ALLOWED_TOP_LEVEL_KEYS = DECLARED_FIELDS | {"schema"}

_GITHUB_HOST = "github.com"
GITHUB_URL_RE = re.compile(
    r"(?:git@|https?://|ssh://git@)([^:/]+)[:/]([^/]+)/([^/]+?)(?:\.git)?/?$"
)


class PlatformGateError(Exception):
    """fail-closed 错误：main 捕获后打印 stderr 并以 exit_code 退出。"""

    def __init__(self, message: str, *, exit_code: int = 2):
        super().__init__(message)
        self.exit_code = exit_code


# ── JSON 变换 ─────────────────────────────────────────────────────────


def strip_descriptions(obj: Any) -> Any:
    """递归删除任意深度的 ``_description`` 注释键（不进 PUT body、不参与比对）。"""
    if isinstance(obj, dict):
        return {
            key: strip_descriptions(value)
            for key, value in obj.items()
            if key != "_description"
        }
    if isinstance(obj, list):
        return [strip_descriptions(item) for item in obj]
    return obj


def strip_readonly_derived(obj: Any) -> Any:
    """递归删除只读派生字段：url / contexts_url / checks / 任意 *_url 键。"""
    if isinstance(obj, dict):
        result: dict[str, Any] = {}
        for key, value in obj.items():
            if key in READONLY_DERIVED_KEYS or key.endswith(READONLY_DERIVED_SUFFIX):
                continue
            result[key] = strip_readonly_derived(value)
        return result
    if isinstance(obj, list):
        return [strip_readonly_derived(item) for item in obj]
    return obj


def contains_key(obj: Any, key: str) -> bool:
    """递归检查对象中是否存在指定键名（测试断言辅助，也用于 body 完整性 guard）。"""
    if isinstance(obj, dict):
        if key in obj:
            return True
        return any(contains_key(value, key) for value in obj.values())
    if isinstance(obj, list):
        return any(contains_key(item, key) for item in obj)
    return False


def _enabled_value(obj: Any) -> bool:
    """归一化形状（{enabled: bool} 对象或裸布尔）→ PUT 形状的布尔。"""
    if isinstance(obj, bool):
        return obj
    if isinstance(obj, dict):
        return bool(obj.get("enabled"))
    return False


def _get_nested(obj: Any, key: str) -> Any:
    """从可能为 None 的对象取键（verify 白名单对 null/缺失字段安全返回 None）。"""
    if not isinstance(obj, dict):
        return None
    return obj.get(key)


# ── 目标 JSON 加载与 schema 校验 ──────────────────────────────────────


def _validate_target(target: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if not isinstance(target, dict):
        return ["目标 JSON 顶层必须是对象"]

    unknown = set(target) - ALLOWED_TOP_LEVEL_KEYS
    if unknown:
        errors.append(f"目标 JSON 含未知顶层字段: {sorted(unknown)}")

    if "schema" in target and not isinstance(target["schema"], str):
        errors.append("`schema` 必须是字符串")

    rsc = target.get("required_status_checks")
    if not isinstance(rsc, dict):
        errors.append("`required_status_checks` 必须是对象")
    else:
        if not isinstance(rsc.get("strict"), bool):
            errors.append("`required_status_checks.strict` 必须是布尔")
        contexts = rsc.get("contexts")
        if not isinstance(contexts, list) or not all(
            isinstance(item, str) and item for item in contexts
        ):
            errors.append("`required_status_checks.contexts` 必须是非空字符串列表")

    conv = target.get("required_conversation_resolution")
    if not isinstance(conv, dict) or not isinstance(conv.get("enabled"), bool):
        errors.append("`required_conversation_resolution.enabled` 必须是布尔")

    reviews = target.get("required_pull_request_reviews")
    count = _get_nested(reviews, "required_approving_review_count")
    if not isinstance(count, int) or isinstance(count, bool) or count < 0:
        errors.append(
            "`required_pull_request_reviews.required_approving_review_count` "
            "必须是非负整数"
        )

    admins = target.get("enforce_admins")
    if not isinstance(admins, dict) or not isinstance(admins.get("enabled"), bool):
        errors.append("`enforce_admins.enabled` 必须是布尔")

    return errors


def load_target(config_path: str) -> dict[str, Any]:
    """加载并校验目标状态 JSON，返回剥离 ``_description`` 后的归一化形状。"""
    try:
        with open(config_path, encoding="utf-8") as handle:
            raw = json.load(handle)
    except FileNotFoundError:
        raise PlatformGateError(f"目标 JSON 不存在: {config_path}")
    except json.JSONDecodeError as exc:
        raise PlatformGateError(f"目标 JSON 非法（无法解析）: {config_path}: {exc}")

    target = strip_descriptions(raw)
    errors = _validate_target(target)
    if errors:
        raise PlatformGateError(
            f"目标 JSON schema 非法: {config_path}; " + "; ".join(errors)
        )
    return target


# ── 子进程（gh / git） ────────────────────────────────────────────────


def _run(args: list[str], *, input_text: str | None = None) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(args, input=input_text, capture_output=True, text=True)
    except OSError as exc:
        raise PlatformGateError(f"执行命令失败: {' '.join(args)}: {exc}")


def _gh_get(repo: str) -> dict[str, Any]:
    proc = _run(["gh", "api", f"repos/{repo}/branches/{MASTER_BRANCH}/protection"])
    if proc.returncode != 0:
        raise PlatformGateError(
            f"gh api GET 失败（exit {proc.returncode}）: {proc.stderr.strip() or '未知错误'}"
        )
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        raise PlatformGateError(f"gh api GET 返回非 JSON: {proc.stdout[:200]}")


def _gh_put(repo: str, payload: dict[str, Any]) -> str:
    proc = _run(
        [
            "gh", "api",
            f"repos/{repo}/branches/{MASTER_BRANCH}/protection",
            "--method", "PUT",
            "--input", "-",
        ],
        input_text=json.dumps(payload),
    )
    if proc.returncode != 0:
        raise PlatformGateError(
            f"gh api PUT 失败（exit {proc.returncode}）: {proc.stderr.strip() or '未知错误'}"
        )
    return proc.stdout


def parse_repo_from_url(url: str) -> str | None:
    """从 SSH/HTTPS remote URL 解析 ``owner/repo``（仅 GitHub 主机）。"""
    match = GITHUB_URL_RE.match(url.strip())
    if not match or match.group(1) != _GITHUB_HOST:
        return None
    return f"{match.group(2)}/{match.group(3)}"


def resolve_repo(repo_flag: str | None) -> str:
    """解析目标仓库。提供 ``--repo`` 时完全短路 git remote 解析。"""
    if repo_flag:
        if "/" not in repo_flag or repo_flag.startswith("/") or repo_flag.endswith("/"):
            raise PlatformGateError(f"--repo 必须是 owner/repo 格式: {repo_flag!r}")
        return repo_flag

    proc = _run(["git", "remote", "get-url", "origin"])
    if proc.returncode != 0:
        raise PlatformGateError(
            f"git remote get-url origin 失败（exit {proc.returncode}）: "
            f"{proc.stderr.strip() or '无 origin remote？'}"
        )
    repo = parse_repo_from_url(proc.stdout)
    if repo is None:
        raise PlatformGateError(
            f"无法从 git remote 解析 GitHub owner/repo（仅支持 github.com）: "
            f"{proc.stdout.strip()!r}。可改用 --repo owner/repo 显式指定。"
        )
    return repo


# ── 比对与 diff ───────────────────────────────────────────────────────


def _scalar_entry(target_val: Any, current_val: Any) -> dict[str, Any]:
    return {
        "target": target_val,
        "current": current_val,
        "match": target_val == current_val,
    }


def _contexts_entry(target_ctx: list[str], current_ctx: Any) -> dict[str, Any]:
    current_list = current_ctx if isinstance(current_ctx, list) else None
    return {
        "target": target_ctx,
        "current": current_ctx,
        "match": (
            current_list is not None
            and sorted(target_ctx) == sorted(current_list)
        ),
    }


def compare(target: dict[str, Any], current: Any) -> dict[str, dict[str, Any]]:
    """白名单比对：只读声明字段，忽略只读派生字段；null/缺失视为漂移（match=False）。"""
    diff: dict[str, dict[str, Any]] = {}

    t_rsc = target.get("required_status_checks") or {}
    c_rsc = _get_nested(current, "required_status_checks")
    if "strict" in t_rsc:
        diff["required_status_checks.strict"] = _scalar_entry(
            t_rsc["strict"], _get_nested(c_rsc, "strict")
        )
    if "contexts" in t_rsc:
        diff["required_status_checks.contexts"] = _contexts_entry(
            t_rsc["contexts"], _get_nested(c_rsc, "contexts")
        )

    t_conv = target.get("required_conversation_resolution") or {}
    if "enabled" in t_conv:
        diff["required_conversation_resolution.enabled"] = _scalar_entry(
            t_conv["enabled"],
            _get_nested(_get_nested(current, "required_conversation_resolution"), "enabled"),
        )

    t_reviews = target.get("required_pull_request_reviews") or {}
    if "required_approving_review_count" in t_reviews:
        diff["required_pull_request_reviews.required_approving_review_count"] = _scalar_entry(
            t_reviews["required_approving_review_count"],
            _get_nested(_get_nested(current, "required_pull_request_reviews"), "required_approving_review_count"),
        )

    t_admins = target.get("enforce_admins") or {}
    if "enabled" in t_admins:
        diff["enforce_admins.enabled"] = _scalar_entry(
            t_admins["enabled"],
            _get_nested(_get_nested(current, "enforce_admins"), "enabled"),
        )

    return diff


def diff_is_match(diff: dict[str, dict[str, Any]]) -> bool:
    """所有已声明字段一致即一致（None 条目不存在：compare 只产出声明字段）。"""
    return all(entry["match"] for entry in diff.values())


def emit_diff(diff: dict[str, dict[str, Any]], label: str) -> None:
    """逐字段 diff 打印到 stderr（目标 vs 实况）；不写 stdout。"""
    print(f"platform-gate: {label}（目标 vs 当前实况）:", file=sys.stderr)
    for field, entry in diff.items():
        marker = "==" if entry["match"] else "!="
        print(
            f"  [{field}] 目标={entry['target']!r} {marker} 实况={entry['current']!r}",
            file=sys.stderr,
        )
    print(
        "  全部一致" if diff_is_match(diff) else "  存在漂移",
        file=sys.stderr,
    )


# ── PUT payload 构造（GET-modify-PUT） ────────────────────────────────


def build_put_payload(
    target: dict[str, Any], current: Any
) -> dict[str, Any]:
    """GET 结果 + 声明字段 merge → 剔除只读派生 → 变换 → 完整 PUT payload。

    四必需字段 enforce_admins / required_pull_request_reviews /
    required_status_checks / restrictions 全部显式给出；未声明的保护字段
    保留自 GET（不重置）；`restrictions` 恒为 null（个人仓 GET 无该字段，
    PUT 语义要求显式传 null 表示不限制）。
    """
    payload: dict[str, Any] = {}

    # enforce_admins：声明覆盖，否则保留 GET；enabled 对象 → 布尔。
    t_admins = target.get("enforce_admins")
    if t_admins is not None:
        payload["enforce_admins"] = _enabled_value(t_admins)
    else:
        payload["enforce_admins"] = _enabled_value(
            _get_nested(current, "enforce_admins")
        )

    # required_pull_request_reviews：保留 GET 可写子字段（dismiss_stale_reviews /
    # require_code_owner_reviews / require_last_push_approval / dismissal_restrictions /
    # bypass_pull_request_allowances），仅用声明覆盖 required_approving_review_count。
    reviews = dict(
        strip_readonly_derived(_get_nested(current, "required_pull_request_reviews") or {})
    )
    t_reviews = target.get("required_pull_request_reviews") or {}
    if "required_approving_review_count" in t_reviews:
        reviews["required_approving_review_count"] = t_reviews[
            "required_approving_review_count"
        ]
    payload["required_pull_request_reviews"] = reviews

    # required_status_checks：剔除 checks/contexts_url，声明覆盖 strict/contexts。
    rsc = dict(
        strip_readonly_derived(_get_nested(current, "required_status_checks") or {})
    )
    t_rsc = target.get("required_status_checks") or {}
    if "strict" in t_rsc:
        rsc["strict"] = t_rsc["strict"]
    if "contexts" in t_rsc:
        rsc["contexts"] = t_rsc["contexts"]
    payload["required_status_checks"] = rsc

    # required_conversation_resolution：声明覆盖，否则保留 GET；enabled → 布尔。
    t_conv = target.get("required_conversation_resolution")
    if t_conv is not None:
        payload["required_conversation_resolution"] = _enabled_value(t_conv)
    else:
        payload["required_conversation_resolution"] = _enabled_value(
            _get_nested(current, "required_conversation_resolution")
        )

    payload["restrictions"] = None

    return strip_descriptions(payload)


# ── CLI 入口 ──────────────────────────────────────────────────────────


def _run_action(args: argparse.Namespace) -> int:
    if shutil.which("gh") is None:
        raise PlatformGateError(
            "gh CLI 不可用（未安装或不在 PATH）；platform-gate 依赖 gh 认证访问 GitHub API"
        )

    target = load_target(args.config)
    repo = resolve_repo(args.repo)
    current = _gh_get(repo)
    diff = compare(target, current)
    label = "verify" if args.verify else "apply 预检"
    emit_diff(diff, label)

    if args.apply:
        payload = build_put_payload(target, current)
        _gh_put(repo, payload)
        result = {
            "ok": True,
            "action": "apply",
            "repo": repo,
            "branch": MASTER_BRANCH,
            "diff": diff,
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    ok = diff_is_match(diff)
    print(
        json.dumps({"ok": ok, "diff": diff}, ensure_ascii=False, indent=2)
    )
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="platform_gate.py",
        description="master 分支保护目标状态幂等配置（--apply GET-modify-PUT；"
        "--verify 只读漂移检测）。stdout 只输出 JSON，diff 与提示走 stderr。",
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--apply", action="store_true", help="把目标状态声明应用到 GitHub branch protection"
    )
    group.add_argument(
        "--verify", action="store_true", help="漂移检测：GET 实况与目标归一化比对，漂移 exit 1"
    )
    parser.add_argument(
        "--config", default=DEFAULT_CONFIG, help=f"目标状态 JSON 路径（默认 {DEFAULT_CONFIG}）"
    )
    parser.add_argument(
        "--repo", default=None, help="覆盖仓库 owner/repo（提供时完全不调用 git remote）"
    )
    args = parser.parse_args(argv)

    try:
        return _run_action(args)
    except PlatformGateError as exc:
        print(f"platform-gate: ERROR: {exc}", file=sys.stderr)
        return exc.exit_code


if __name__ == "__main__":
    sys.exit(main())
