#!/usr/bin/env python3
"""Read-only phase completion verification. Never modifies files.

Usage:
    uv run python scripts/check_phase_done.py --phase wayfinding --change <id>
    uv run python scripts/check_phase_done.py --phase planning --change <id>
    uv run python scripts/check_phase_done.py --phase building --change <id>
    uv run python scripts/check_phase_done.py --phase closing --change <id>
    uv run python scripts/check_phase_done.py --phase wayfinding --change <id> --json

Document artifact checks are delegated to the configured DocArtifactProtocol
implementation (default: OpenSpec). Functional checks (pytest, benchmark smoke,
openspec CLI validation) stay here because they are not artifact-related.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from importlib import import_module
from pathlib import Path

# Ensure repo root is on sys.path so agent.* imports resolve.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from agent.workflow.resume_audit import run_resume_audit  # noqa: E402
from agent.workflow.routing import is_workflow_enabled  # noqa: E402

VALID_PHASES = {"wayfinding", "planning", "building", "closing"}


# ── protocol loading (lazy, cached) ──────────────────────────────────


def _load_methods() -> dict:
    """Load workflow_methods.json from the scripts directory."""
    methods_path = Path(__file__).resolve().parent / "workflow_methods.json"
    if not methods_path.exists():
        return {}
    try:
        return json.loads(methods_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _get_doc_artifact_config() -> dict:
    """Extract the doc_artifact section from workflow methods config."""
    methods = _load_methods()
    return methods.get("doc_artifact", {})


def _get_doc_artifact_paths() -> dict[str, str]:
    return _get_doc_artifact_config().get("paths", {})


def _workflow_disabled() -> bool:
    return not is_workflow_enabled(_REPO_ROOT)


def _resume_audit_errors() -> list[str]:
    return list(run_resume_audit(_REPO_ROOT).errors)


_PROTOCOL_INSTANCE = None


def _get_protocol():
    """Load and cache the configured DocArtifactProtocol instance."""
    global _PROTOCOL_INSTANCE
    if _PROTOCOL_INSTANCE is not None:
        return _PROTOCOL_INSTANCE

    config = _get_doc_artifact_config()
    protocol_module = config.get(
        "protocol", "agent.workflow.doc_artifact_protocol_openspec"
    )
    paths = config.get("paths", {})

    try:
        mod = import_module(protocol_module)
        # Find the protocol implementation class
        cls = getattr(mod, "OpenSpecDocArtifactProtocol", None)
        if cls is None:
            # Fallback: find any class implementing DocArtifactProtocol
            from agent.workflow.doc_artifact_protocol import DocArtifactProtocol

            for attr in dir(mod):
                obj = getattr(mod, attr)
                if (
                    isinstance(obj, type)
                    and issubclass(obj, DocArtifactProtocol)
                    and obj is not DocArtifactProtocol
                ):
                    cls = obj
                    break
        if cls is None:
            raise ImportError(f"No DocArtifactProtocol impl found in {protocol_module}")
        _PROTOCOL_INSTANCE = cls(paths)
    except Exception:
        # Fallback to OpenSpec default
        from agent.workflow.doc_artifact_protocol_openspec import (
            OpenSpecDocArtifactProtocol,
        )

        _PROTOCOL_INSTANCE = OpenSpecDocArtifactProtocol(paths)

    return _PROTOCOL_INSTANCE


# ── path helpers (derived from protocol config) ─────────────────────


def _changes_root() -> Path:
    paths = _get_doc_artifact_paths()
    tmpl = paths.get("change_dir_template", "openspec/changes/{change_id}")
    # Extract the base: everything before {change_id}
    base = tmpl.split("/{")[0] if "/{" in tmpl else tmpl.rsplit("/", 1)[0]
    return Path(base)


def _handoff_dir() -> Path:
    paths = _get_doc_artifact_paths()
    return Path(paths.get("handoff_dir", ".handoff"))


def _known_debt_path() -> Path:
    paths = _get_doc_artifact_paths()
    return Path(paths.get("known_debt_path", "docs/known-debt.md"))


def _known_issues_path() -> Path:
    paths = _get_doc_artifact_paths()
    return Path(paths.get("known_issues_path", "docs/known-issues.md"))


# ── helpers ────────────────────────────────────────────────────────────


def _load_known_issues() -> dict[str, set[str]]:
    """Load pre-existing known issues exempted from gate checks.

    Known issues file format:
        ## Pytest Patterns
        - tests.support
        - test_collection_error_pattern

        ## TODO Patterns
        - some_exact_todo_line_content
    """
    result: dict[str, set[str]] = {"pytest": set(), "todo": set()}
    kip = _known_issues_path()
    if not kip.exists():
        return result
    current_key = ""
    for line in kip.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("## Pytest"):
            current_key = "pytest"
        elif stripped.startswith("## TODO"):
            current_key = "todo"
        elif stripped.startswith("- ") and current_key:
            result[current_key].add(stripped[2:].strip())
    return result


def _load_handoff(change_id: str) -> dict | None:
    changes = _changes_root()
    path = changes / change_id / "handoff.json"
    if not path.exists():
        archive_matches = list((changes / "archive").glob(f"*{change_id}*"))
        if archive_matches:
            hf = archive_matches[0] / "handoff.json"
            if hf.exists():
                return json.loads(hf.read_text(encoding="utf-8"))
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _load_known_debt() -> set[str]:
    kdp = _known_debt_path()
    if not kdp.exists():
        return set()
    entries: set[str] = set()
    for line in kdp.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and not stripped.startswith("- "):
            entries.add(stripped)
        elif stripped.startswith("- "):
            entries.add(stripped[2:].strip())
    return entries


def _changed_python_files(repo_root: Path) -> list[Path]:
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", "origin/master", "--", "*.py"],
            capture_output=True, text=True, cwd=repo_root,
        )
    except FileNotFoundError:
        return []
    if result.returncode != 0:
        return []
    return [repo_root / p for p in result.stdout.strip().splitlines() if p]


def _find_todo_residuals(repo_root: Path, change_id: str) -> list[str]:
    known = _load_known_debt()
    changed = _changed_python_files(repo_root)
    changed = [p for p in changed if "check_phase_done" not in p.name
               and "test_check_phase_done" not in p.name]
    residuals: list[str] = []
    for fpath in changed:
        if not fpath.exists():
            continue
        try:
            text = fpath.read_text(encoding="utf-8")
        except Exception:
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            stripped = line.strip()
            if not stripped:
                continue
            if any(marker in stripped for marker in ("TODO", "TBD", "FIXME", "HACK")):
                if stripped not in known:
                    residuals.append(f"{fpath.relative_to(repo_root)}:{lineno}: {stripped}")
    return residuals


def _benchmark_smoke_passes(repo_root: Path) -> tuple[bool, str]:
    try:
        result = subprocess.run(
            [
                "uv", "run", "asterwynd", "benchmark", "benchmarks/tasks",
                "--agent", "fake", "--source-repo", str(repo_root),
                "--runs-dir", "/tmp/smoke-check",
            ],
            capture_output=True, text=True, cwd=repo_root, timeout=120,
        )
        return result.returncode == 0, result.stdout[-500:] if result.stdout else result.stderr
    except FileNotFoundError:
        return True, "SKIP: uv/asterwynd 命令不可用"
    except subprocess.TimeoutExpired:
        return False, "Benchmark smoke 超时 (120s)"


def _check_review_report(change_id: str, phase: str, report_name: str | None = None) -> list[str]:
    """Check that a review report exists and has no blockers."""
    errors: list[str] = []
    if report_name is None:
        report_name = f"{phase}-review.md"
    hd = _handoff_dir()
    report_path = hd / change_id / report_name
    if not report_path.exists():
        errors.append(f"审阅报告缺失: {report_path} — 尚未运行独立子 Agent 审阅")
    else:
        try:
            text = report_path.read_text(encoding="utf-8")
            if "BLOCKED" in text:
                errors.append(f"审阅报告包含 BLOCKED — 存在未解决的阻塞项: {report_path}")
            elif "CHANGES_REQUESTED" in text:
                errors.append(f"审阅报告包含 CHANGES_REQUESTED — 请确认所有修改请求已解决: {report_path}")
            else:
                from agent.workflow.review_manifest import verify_review_manifest

                errors.extend(verify_review_manifest(hd.parent, change_id, phase))
        except Exception:
            errors.append(f"无法读取审阅报告: {report_path}")
    return errors


def _check_subagent_calls(change_id: str, phase: str) -> list[str]:
    """Verify sub-agent calls were recorded for reviewing_* sub-states.

    Reads require_subagent config from workflow_methods.json and agent call
    records from .handoff/<change_id>/_agent-calls.json.
    """
    errors: list[str] = []
    try:
        methods = _load_methods()
        phase_cfg = methods.get(phase, {})
        hd = _handoff_dir()
        for sub_state, cfg in phase_cfg.items():
            if not isinstance(cfg, dict) or not cfg.get("require_subagent"):
                continue
            log_path = hd / change_id / "_agent-calls.json"
            if not log_path.exists():
                errors.append(
                    f"子Agent调用记录缺失: {sub_state} 要求 spawn 独立子Agent审阅，"
                    f"但未检测到 Agent 工具调用。"
                    f"请用 /{cfg.get('method','code-review')} spawn 子Agent。"
                )
                continue
            try:
                calls = json.loads(log_path.read_text(encoding="utf-8"))
                matching = [c for c in calls if c.get("sub_state") == sub_state]
                if not matching:
                    errors.append(
                        f"子Agent调用记录缺失: {sub_state} 要求 spawn 子Agent，"
                        f"但 _agent-calls.json 中无匹配记录。"
                    )
            except Exception:
                errors.append(f"无法读取子Agent调用记录: {log_path}")
    except Exception:
        pass
    return errors


def _check_handoff_at_gate(change_id: str, phase: str) -> list[str]:
    """Verify handoff.json is at the correct phase and gate sub-state."""
    errors: list[str] = []
    data = _load_handoff(change_id)
    if data is None:
        errors.append("handoff.json 不存在")
    else:
        state = data.get("state", {})
        actual_phase = state.get("phase")
        valid_phases = {phase}
        if phase == "closing":
            valid_phases.add("done")
        if actual_phase not in valid_phases:
            errors.append(f"期望 phase in {valid_phases}，实际={actual_phase}")
        if actual_phase != "done" and state.get("sub_state") != "ready_for_review":
            errors.append(
                f"期望 sub_state=ready_for_review，实际={state.get('sub_state')}"
            )
    return errors


# ── phase checkers ─────────────────────────────────────────────────────


def check_wayfinding(change_id: str) -> list[str]:
    if _workflow_disabled():
        return []
    errors: list[str] = _resume_audit_errors()
    change_dir = _changes_root() / change_id

    if not change_dir.exists():
        return errors + [f"Change 目录不存在: {change_dir}"]

    # Delegate artifact checks to protocol
    try:
        protocol = _get_protocol()
        repo_root = Path.cwd()
        result = protocol.check_phase_artifacts(
            "wayfinding", change_id, change_dir, repo_root
        )
        for check in result.checks:
            if not check.passed and check.is_blocking:
                errors.append(check.detail)
    except Exception as e:
        errors.append(f"Protocol check failed: {e}")

    # Review report
    review_errors = _check_review_report(change_id, "wayfinding")
    errors.extend(review_errors)

    # handoff.json at gate
    errors.extend(_check_handoff_at_gate(change_id, "wayfinding"))

    return errors


def check_planning(change_id: str) -> list[str]:
    if _workflow_disabled():
        return []
    errors: list[str] = _resume_audit_errors()
    change_dir = _changes_root() / change_id

    if not change_dir.exists():
        return errors + [f"Change 目录不存在: {change_dir}"]

    # Delegate ALL artifact checks to protocol (replaces direct
    # check_openspec_artifacts.check_change call)
    try:
        protocol = _get_protocol()
        repo_root = Path.cwd()
        specs_root = repo_root / _get_doc_artifact_paths().get(
            "specs_dir", "openspec/specs"
        )
        result = protocol.check_phase_artifacts(
            "planning", change_id, change_dir, repo_root
        )
        for check in result.checks:
            if not check.passed and check.is_blocking:
                errors.append(check.detail)
    except Exception as e:
        errors.append(f"Protocol artifact check failed: {e}")

    # Review report
    review_errors = _check_review_report(change_id, "planning")
    errors.extend(review_errors)

    # handoff.json at gate
    errors.extend(_check_handoff_at_gate(change_id, "planning"))

    return errors


def check_building(change_id: str, repo_root: Path | None = None) -> list[str]:
    if _workflow_disabled():
        return []
    errors: list[str] = _resume_audit_errors()
    root = repo_root or Path.cwd()
    known_issues = _load_known_issues()

    # ── functional checks (not document artifacts) ──

    # 1. pytest passes
    try:
        result = subprocess.run(
            ["uv", "run", "pytest", "-q",
             "--ignore=tests/web_tests", "--ignore=tests/test_cli.py",
             "--ignore=tests/benchmark", "--ignore=tests/support"],
            capture_output=True, text=True, cwd=root, timeout=300,
        )
        if result.returncode != 0:
            all_lines = (result.stdout or result.stderr).strip().splitlines()
            error_lines = [
                l for l in all_lines
                if "ERROR" in l or "ModuleNotFound" in l or "ImportError" in l
            ]
            # Also collect FAILED summary lines (contain test name + file path)
            failed_lines = [l for l in all_lines if "FAILED" in l]
            if not error_lines and not failed_lines:
                error_lines = [l for l in all_lines if l.strip()]
            else:
                error_lines = error_lines + failed_lines
            known_patterns = known_issues.get("pytest", set())
            unknown_lines = [
                l for l in error_lines
                if not any(p in l for p in known_patterns)
            ]
            if unknown_lines:
                errors.append(
                    f"pytest 未通过 (exit={result.returncode}):\n"
                    + "\n".join(unknown_lines[:5])
                )
    except FileNotFoundError:
        errors.append("SKIP: uv/pytest 不可用")
    except subprocess.TimeoutExpired:
        errors.append("pytest 超时 (300s)")

    # 2. No TODO/TBD residuals in changed files
    residuals = _find_todo_residuals(root, change_id)
    if residuals:
        known_todos = known_issues.get("todo", set())
        unknown = [r for r in residuals if not any(kt in r for kt in known_todos)]
        if unknown:
            errors.append(
                f"发现 {len(unknown)} 处 TODO/TBD/FIXME/HACK 残留:\n"
                + "\n".join(f"  {r}" for r in unknown[:10])
            )

    # 3. Benchmark smoke
    passed, reason = _benchmark_smoke_passes(root)
    if not passed:
        errors.append(f"Benchmark smoke 未通过: {reason}")

    # ── document artifact checks (delegated to protocol) ──

    change_dir = _changes_root() / change_id
    if change_dir.exists():
        try:
            protocol = _get_protocol()
            result = protocol.check_phase_artifacts(
                "building", change_id, change_dir, root
            )
            for check in result.checks:
                if not check.passed and check.is_blocking:
                    errors.append(check.detail)
        except Exception as e:
            errors.append(f"Protocol artifact check failed: {e}")

    # ── workflow checks ──

    # 4. Review report (basic existence check; content is in protocol)
    review_errors = _check_review_report(change_id, "building")
    errors.extend(review_errors)

    # 5. handoff.json at building.ready_for_review
    errors.extend(_check_handoff_at_gate(change_id, "building"))

    # 6. Sub-agent call verification
    errors.extend(_check_subagent_calls(change_id, "building"))

    return errors


def check_closing(change_id: str) -> list[str]:
    if _workflow_disabled():
        return []
    errors: list[str] = _resume_audit_errors()

    # ── functional check: openspec validate CLI ──

    try:
        result = subprocess.run(
            ["npx", "--yes", "@fission-ai/openspec@1.4.1", "validate", "--all", "--strict"],
            capture_output=True, text=True, timeout=120,
        )
        if result.returncode != 0:
            errors.append(f"openspec validate 未通过: {result.stdout[-300:] or result.stderr}")
    except FileNotFoundError:
        errors.append("SKIP: npx/openspec 不可用")
    except subprocess.TimeoutExpired:
        errors.append("openspec validate 超时 (120s)")

    # ── document artifact checks (delegated to protocol) ──

    repo_root = Path.cwd()
    change_dir = _changes_root() / change_id
    try:
        protocol = _get_protocol()
        result = protocol.check_phase_artifacts(
            "closing", change_id, change_dir, repo_root
        )
        for check in result.checks:
            if not check.passed and check.is_blocking:
                errors.append(check.detail)
    except Exception as e:
        errors.append(f"Protocol artifact check failed: {e}")

    # ── workflow checks ──

    # Review report
    review_errors = _check_review_report(change_id, "closing")
    errors.extend(review_errors)

    # handoff.json at closing.ready_for_review or done
    errors.extend(_check_handoff_at_gate(change_id, "closing"))

    return errors


# ── CLI ─────────────────────────────────────────────────────────────────


def main() -> int:
    parser = argparse.ArgumentParser(
        description="只读 phase 完成验证 — 不修改任何文件。Gate 处运行。",
    )
    parser.add_argument("--phase", required=True, choices=sorted(VALID_PHASES))
    parser.add_argument("--change", required=True, help="Change ID")
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--json", action="store_true", help="JSON 输出")

    args = parser.parse_args()
    root = Path(args.repo_root).resolve()

    checkers = {
        "wayfinding": lambda: check_wayfinding(args.change),
        "planning": lambda: check_planning(args.change),
        "building": lambda: check_building(args.change, root),
        "closing": lambda: check_closing(args.change),
    }

    errors = checkers[args.phase]()

    if args.json:
        print(json.dumps({
            "phase": args.phase,
            "change_id": args.change,
            "passed": len(errors) == 0,
            "errors": errors,
            "checks_run": len(errors) if errors else 1,
        }, indent=2, ensure_ascii=False))
    else:
        if errors:
            for e in errors:
                print(f"FAIL: {e}")
            print(f"\n{len(errors)} 项检查失败")
        else:
            print(f"PASS: {args.phase} 阶段所有检查已通过")

    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
