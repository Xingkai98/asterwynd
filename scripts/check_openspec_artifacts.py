#!/usr/bin/env python3
"""Check project-level OpenSpec artifact rules.

This checker intentionally performs mechanical checks only:

- required files exist for the declared change type set
- required sections exist and contain non-placeholder body text
- proposal.md declares Change Type with primary/secondary fields
- change spec delta capabilities map to current specs
- non-docs changes with spec deltas include a current spec sync task
- non-docs changes include Impact Analysis
- non-docs changes include Reference Implementation Research decision records
- changes that require design include a Pre-Implementation Review record
- handoff.json structure validation (when present)

It does not judge whether a design is technically correct. Human review owns
that gate.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


ALLOWED_TYPES = {"feature", "bugfix", "research", "docs", "process", "refactor"}
DESIGN_TYPES = {"feature", "refactor", "process"}
DIAGNOSIS_TYPES = {"bugfix", "research"}

BENCHMARK_SMOKE_CAPABILITIES = {
    "agent-runtime",
    "benchmark",
    "coding-tools",
    "tool-system",
    "workspace-safety",
}
BENCHMARK_SMOKE_CODE_PATTERNS = (
    r"`?agent/loop\.py`?",
    r"`?agent/tools/",
    r"`?agent/workspace_policy\.py`?",
    r"`?benchmarks/",
)
BACKLOG_CHANGE_PATTERN = re.compile(r"###\s+\d+\.\s+`([^`]+)`")
DONE_BACKLOG_PATTERN = re.compile(r"-\s+`([^`]+)`")

DESIGN_SECTIONS = [
    "Context",
    "Goals / Non-Goals",
    "Decisions",
    "Pre-Implementation Review",
    "Risks / Trade-offs",
    "Testing Strategy",
]
DIAGNOSIS_SECTIONS = [
    "Symptom",
    "Reproduction",
    "Evidence",
    "Root Cause",
    "Recommended Direction",
    "Regression Tests",
]
REFERENCE_RESEARCH_SECTION = "Reference Implementation Research"
REFERENCE_RESEARCH_FIELDS = (
    "status",
    "reason",
    "research questions",
    "findings",
    "design impact",
)

PLACEHOLDER_ONLY = {
    "todo",
    "tbd",
    "n/a",
    "na",
    "待补充",
    "无",
}
PROTECTED_ARTIFACT_EVENT = "protected_artifact_explained"
CURRENT_SPEC_SYNC_EVENT = "current_spec_synced"
BACKLOG_UPDATED_EVENT = "backlog_updated"
CHANGE_ARCHIVED_EVENT = "change_archived"
PROTECTED_PATH_RULES = (
    ("exact", "docs/known-debt.md", (PROTECTED_ARTIFACT_EVENT,)),
    ("exact", "docs/known-issues.md", (PROTECTED_ARTIFACT_EVENT,)),
    ("exact", "docs/openspec-change-backlog.md", (BACKLOG_UPDATED_EVENT,)),
    ("prefix", "openspec/specs/", (CURRENT_SPEC_SYNC_EVENT,)),
    ("prefix", "openspec/changes/archive/", (CHANGE_ARCHIVED_EVENT,)),
)


@dataclass(frozen=True)
class ChangeType:
    primary: str
    secondary: tuple[str, ...]

    @property
    def all_types(self) -> set[str]:
        return {self.primary, *self.secondary}


def _strip_markdown_noise(text: str) -> str:
    text = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)
    lines = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        stripped = re.sub(r"^[-*]\s+", "", stripped)
        stripped = re.sub(r"^\d+\.\s+", "", stripped)
        stripped = stripped.strip("`*_ ")
        if stripped:
            lines.append(stripped)
    return "\n".join(lines).strip()


def _is_placeholder_body(text: str) -> bool:
    if "<!--" in text and "-->" in text and not _strip_markdown_noise(text):
        return True
    cleaned = _strip_markdown_noise(text).lower()
    if not cleaned:
        return True
    return cleaned in PLACEHOLDER_ONLY


def _extract_h2_sections(text: str) -> dict[str, str]:
    matches = list(re.finditer(r"^##\s+(.+?)\s*$", text, flags=re.MULTILINE))
    sections: dict[str, str] = {}
    for index, match in enumerate(matches):
        title = match.group(1).strip()
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        sections[title] = text[start:end].strip()
    return sections


def _parse_list_value(value: str) -> tuple[str, ...]:
    value = value.strip()
    if not value or value in {"[]", "-"}:
        return ()
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        if not inner:
            return ()
        return tuple(part.strip().strip("'\"") for part in inner.split(",") if part.strip())
    return (value.strip().strip("'\""),)


def parse_change_type(proposal_text: str) -> tuple[ChangeType | None, list[str]]:
    errors: list[str] = []
    sections = _extract_h2_sections(proposal_text)
    body = sections.get("Change Type")
    if body is None:
        return None, ["proposal.md missing required section: ## Change Type"]

    primary: str | None = None
    secondary: tuple[str, ...] = ()

    for raw_line in body.splitlines():
        line = raw_line.strip()
        if line.startswith("-"):
            line = line[1:].strip()
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip().lower()
        value = value.strip()
        if key == "primary":
            parsed = _parse_list_value(value)
            primary = parsed[0] if parsed else ""
        elif key == "secondary":
            secondary = _parse_list_value(value)

    if not primary:
        errors.append("## Change Type must declare `primary: <type>`")
        return None, errors

    declared = [primary, *secondary]
    invalid = [item for item in declared if item not in ALLOWED_TYPES]
    if invalid:
        errors.append(
            "invalid change type(s): "
            + ", ".join(invalid)
            + f" (allowed: {', '.join(sorted(ALLOWED_TYPES))})"
        )
    if primary in secondary:
        errors.append("secondary must not repeat primary type")

    if errors:
        return None, errors
    return ChangeType(primary=primary, secondary=secondary), []


def _check_required_sections(path: Path, required_sections: list[str]) -> list[str]:
    errors: list[str] = []
    if not path.exists():
        return [f"missing required file: {path.name}"]

    sections = _extract_h2_sections(path.read_text(encoding="utf-8"))
    for section in required_sections:
        if section not in sections:
            errors.append(f"{path.name} missing required section: ## {section}")
            continue
        if _is_placeholder_body(sections[section]):
            errors.append(f"{path.name} section is empty or placeholder-only: ## {section}")
    return errors


def _check_impact_analysis(change_dir: Path, proposal_text: str) -> list[str]:
    proposal_sections = _extract_h2_sections(proposal_text)
    if "Impact Analysis" in proposal_sections:
        if _is_placeholder_body(proposal_sections["Impact Analysis"]):
            return ["proposal.md section is empty or placeholder-only: ## Impact Analysis"]
        return []

    design = change_dir / "design.md"
    if design.exists():
        design_sections = _extract_h2_sections(design.read_text(encoding="utf-8"))
        if "Impact Analysis" in design_sections:
            if _is_placeholder_body(design_sections["Impact Analysis"]):
                return ["design.md section is empty or placeholder-only: ## Impact Analysis"]
            return []

    return ["proposal.md or design.md missing required section: ## Impact Analysis"]


def _extract_record_field(section_body: str, field: str) -> str | None:
    lines = section_body.splitlines()
    field_prefix = f"{field.lower()}:"
    all_prefixes = tuple(f"{item}:" for item in REFERENCE_RESEARCH_FIELDS)

    for index, line in enumerate(lines):
        stripped = re.sub(r"^\s*[-*]\s+", "", line).strip()
        if not stripped.lower().startswith(field_prefix):
            continue

        value = stripped.split(":", 1)[1].strip()
        collected = [value] if value else []
        for next_line in lines[index + 1 :]:
            next_stripped = re.sub(r"^\s*[-*]\s+", "", next_line).strip().lower()
            if any(next_stripped.startswith(prefix) for prefix in all_prefixes):
                break
            collected.append(next_line)
        return "\n".join(collected).strip()

    return None


def _find_reference_research_section(
    change_dir: Path, proposal_text: str
) -> tuple[str, str] | None:
    proposal_sections = _extract_h2_sections(proposal_text)
    if REFERENCE_RESEARCH_SECTION in proposal_sections:
        return "proposal.md", proposal_sections[REFERENCE_RESEARCH_SECTION]

    design = change_dir / "design.md"
    if design.exists():
        design_sections = _extract_h2_sections(design.read_text(encoding="utf-8"))
        if REFERENCE_RESEARCH_SECTION in design_sections:
            return "design.md", design_sections[REFERENCE_RESEARCH_SECTION]

    return None


def _check_reference_implementation_research(
    change_dir: Path, proposal_text: str, change_type: ChangeType
) -> list[str]:
    if change_type.primary == "docs":
        return []

    found = _find_reference_research_section(change_dir, proposal_text)
    if found is None:
        return [
            "proposal.md or design.md missing required section: "
            f"## {REFERENCE_RESEARCH_SECTION}"
        ]

    source, body = found
    if _is_placeholder_body(body):
        return [
            f"{source} section is empty or placeholder-only: "
            f"## {REFERENCE_RESEARCH_SECTION}"
        ]

    status = _extract_record_field(body, "status")
    if status is None or _is_placeholder_body(status):
        return [
            f"{source} section must declare `status: enabled` or "
            f"`status: disabled`: ## {REFERENCE_RESEARCH_SECTION}"
        ]

    normalized_status = status.splitlines()[0].strip().lower()
    if normalized_status not in {"enabled", "disabled"}:
        return [
            f"{source} section has invalid reference implementation research "
            f"status `{normalized_status}` (allowed: enabled, disabled)"
        ]

    errors: list[str] = []
    reason = _extract_record_field(body, "reason")
    if reason is None or _is_placeholder_body(reason):
        errors.append(
            f"{source} section must include non-empty `reason`: "
            f"## {REFERENCE_RESEARCH_SECTION}"
        )

    if normalized_status == "enabled":
        for field in ("research questions", "findings", "design impact"):
            value = _extract_record_field(body, field)
            if value is None or _is_placeholder_body(value):
                errors.append(
                    f"{source} section must include non-empty `{field}` when "
                    f"reference implementation research is enabled: "
                    f"## {REFERENCE_RESEARCH_SECTION}"
                )

    return errors


def _requires_benchmark_smoke(proposal_text: str) -> bool:
    lowered = proposal_text.lower()
    for capability in BENCHMARK_SMOKE_CAPABILITIES:
        if f"- `{capability}`" in lowered or f"`{capability}`:" in lowered:
            return True
    return any(re.search(pattern, proposal_text) for pattern in BENCHMARK_SMOKE_CODE_PATTERNS)


def _has_benchmark_smoke_task(tasks_text: str) -> bool:
    lowered = tasks_text.lower()
    return "benchmark" in lowered and "smoke" in lowered


def _has_design_review_task(tasks_text: str) -> bool:
    lowered = tasks_text.lower()
    return (
        "grill-with-docs" in lowered
        or "batch-grill" in lowered
        or "等价设计追问" in tasks_text
    )


def _has_current_spec_sync_task(tasks_text: str) -> bool:
    lowered = tasks_text.lower()
    return (
        ("current spec" in lowered or "当前规格" in tasks_text)
        and "openspec/specs" in lowered
    )


def _changed_capabilities(change_dir: Path) -> tuple[str, ...]:
    specs_root = change_dir / "specs"
    if not specs_root.exists():
        return ()
    return tuple(
        sorted(
            path.parent.name
            for path in specs_root.glob("*/spec.md")
            if path.is_file()
        )
    )


def _check_current_spec_mapping(
    change_dir: Path, current_specs_root: Path | None
) -> list[str]:
    capabilities = _changed_capabilities(change_dir)
    if not capabilities:
        return []

    root = current_specs_root or change_dir.parent.parent / "specs"
    errors: list[str] = []
    for capability in capabilities:
        current_spec = root / capability / "spec.md"
        if not current_spec.exists():
            errors.append(
                "spec delta capability "
                f"`{capability}` has no matching current spec at {current_spec}"
            )
    return errors


def _check_current_spec_sync_task(
    change_dir: Path, change_type: ChangeType
) -> list[str]:
    if change_type.primary == "docs" or not _changed_capabilities(change_dir):
        return []

    tasks = change_dir / "tasks.md"
    if not tasks.exists():
        return ["missing required file: tasks.md"]
    if not _has_current_spec_sync_task(tasks.read_text(encoding="utf-8")):
        return [
            "tasks.md missing current spec sync task for spec delta "
            "(`openspec/specs/<capability>/spec.md`)"
        ]
    return []


def _check_design_review_task(change_dir: Path, change_type: ChangeType) -> list[str]:
    if not (change_type.all_types & DESIGN_TYPES):
        return []

    tasks = change_dir / "tasks.md"
    if not tasks.exists():
        return ["missing required file: tasks.md"]
    if not _has_design_review_task(tasks.read_text(encoding="utf-8")):
        return [
            "tasks.md missing pre-implementation batch-grill-me (grill-with-docs) or equivalent design review task"
        ]
    return []


def _check_benchmark_smoke_task(change_dir: Path, proposal_text: str) -> list[str]:
    if not _requires_benchmark_smoke(proposal_text):
        return []

    tasks = change_dir / "tasks.md"
    if not tasks.exists():
        return ["missing required file: tasks.md"]
    if not _has_benchmark_smoke_task(tasks.read_text(encoding="utf-8")):
        return [
            "tasks.md missing benchmark smoke verification item for coding-agent core change"
        ]
    return []


HANDOFF_REQUIRED_FIELDS = ["schema_version", "change_id", "state", "transitions"]
HANDOFF_STATE_FIELDS = ["phase", "sub_state"]
# Four-phase workflow model: wayfinding → planning → building → closing
# reviewing and code-review are now reviewing_* sub-states within each phase
VALID_PHASES = {"wayfinding", "planning", "building", "closing", "blocked", "done"}
VALID_ROUTING_PHASES = {"wayfinding", "planning", "building", "closing"}


def _check_handoff_json(change_dir: Path) -> list[str]:
    handoff = change_dir / "handoff.json"
    if not handoff.exists():
        return []

    errors: list[str] = []
    change_name = change_dir.name

    try:
        data = json.loads(handoff.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [f"{change_name}: handoff.json is not valid JSON: {exc}"]

    if not isinstance(data, dict):
        return [f"{change_name}: handoff.json must be a JSON object"]

    for field in HANDOFF_REQUIRED_FIELDS:
        if field not in data:
            errors.append(f"{change_name}: handoff.json missing required field: {field}")

    if "state" in data:
        state = data["state"]
        if not isinstance(state, dict):
            errors.append(f"{change_name}: handoff.json state must be an object")
        else:
            for field in HANDOFF_STATE_FIELDS:
                if field not in state:
                    errors.append(f"{change_name}: handoff.json state missing field: {field}")
            phase = state.get("phase")
            if phase is not None and phase not in VALID_PHASES:
                errors.append(
                    f"{change_name}: handoff.json state.phase invalid: {phase!r}, "
                    f"expected one of {sorted(VALID_PHASES)}"
                )

    if "transitions" in data and not isinstance(data["transitions"], list):
        errors.append(f"{change_name}: handoff.json transitions must be an array")

    if "routing" in data:
        routing = data["routing"]
        if not isinstance(routing, dict):
            errors.append(f"{change_name}: handoff.json routing must be an object")
        else:
            for phase in VALID_ROUTING_PHASES:
                if phase not in routing:
                    errors.append(f"{change_name}: handoff.json routing missing phase: {phase}")
                else:
                    entry = routing[phase]
                    if not isinstance(entry, dict):
                        errors.append(
                            f"{change_name}: handoff.json routing.{phase} must be an object"
                        )
                    else:
                        if "executor" not in entry:
                            errors.append(
                                f"{change_name}: handoff.json routing.{phase} missing executor"
                            )
                        if "session_mode" not in entry:
                            errors.append(
                                f"{change_name}: handoff.json routing.{phase} missing session_mode"
                            )

    if "blockers" in data and not isinstance(data["blockers"], list):
        errors.append(f"{change_name}: handoff.json blockers must be an array")

    if (change_dir / "workflow-events.jsonl").exists():
        from agent.workflow.event_log import verify_handoff_projection

        errors.extend(verify_handoff_projection(change_dir))

    return errors


def _repo_root_for_change_dir(change_dir: Path) -> Path:
    if (
        change_dir.parent.name == "changes"
        and change_dir.parent.parent.name == "openspec"
    ):
        return change_dir.parent.parent.parent
    return change_dir.parent


def _tasks_all_complete(change_dir: Path) -> bool:
    """Return True when every checkbox line in tasks.md is ``[x]``.

    A tasks.md with no checkbox lines is treated as incomplete (no evidence of
    implementation), so the review gate does not fire prematurely.
    """
    tasks = change_dir / "tasks.md"
    if not tasks.exists():
        return False
    text = tasks.read_text(encoding="utf-8")
    checked = 0
    unchecked = 0
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("- [x]") or stripped.startswith("* [x]"):
            checked += 1
        elif stripped.startswith("- [ ]") or stripped.startswith("* [ ]"):
            unchecked += 1
    return checked > 0 and unchecked == 0


def _check_review_manifests(change_dir: Path, change_type: ChangeType) -> list[str]:
    # Review evidence lives inside the change directory (reviews/), so it is
    # committed with the change and CI can verify it mechanically. See
    # agent/workflow/review_manifest.py.
    review_dir = change_dir / "reviews"
    review_report = review_dir / "building-review.md"

    # Mandatory building review for non-docs changes that ship code: the
    # independent subagent review closed loop (issue #90) must have run and
    # produced a PASS manifest before the change is merged. docs-only changes
    # skip this gate. The gate only fires once the change's tasks are ALL
    # checked — proposal-stage / partially-implemented changes (whose spec
    # delta already exists) must not be flagged, or CI would block every
    # in-flight change.
    requires_building_review = (
        change_type.primary != "docs"
        and _changed_capabilities(change_dir)
        and _tasks_all_complete(change_dir)
    )

    if requires_building_review and not review_report.exists():
        return [
            "building-review.md missing — 独立 subagent 审阅未运行。"
            "请用 /review-loop 跑审阅闭环（审→改→再审直到 PASS 或 3 轮封顶）。"
        ]

    if not review_dir.exists():
        return []

    from agent.workflow.review_manifest import verify_review_manifest

    repo_root = _repo_root_for_change_dir(change_dir)
    errors: list[str] = []
    for report_path in sorted(review_dir.glob("*-review.md")):
        phase = report_path.name.removesuffix("-review.md")
        errors.extend(verify_review_manifest(repo_root, change_dir.name, phase))
    return errors


def check_protected_path_explanations(
    repo_root: Path,
    *,
    changed_paths: set[str],
) -> list[str]:
    errors: list[str] = []
    for path in sorted(changed_paths):
        allowed_event_types = _allowed_event_types_for_protected_path(path)
        if allowed_event_types is None:
            continue
        explanation_errors = _protected_artifact_explanation_errors(
            repo_root,
            path,
            allowed_event_types=allowed_event_types,
        )
        if explanation_errors is None:
            errors.append(
                f"protected path `{path}` changed without workflow event explanation"
            )
        else:
            errors.extend(explanation_errors)
    return errors


def _protected_artifact_explanation_errors(
    repo_root: Path,
    artifact_path: str,
    *,
    allowed_event_types: tuple[str, ...],
) -> list[str] | None:
    changes_root = repo_root / "openspec" / "changes"
    if not changes_root.exists():
        return None

    matching_errors: list[str] = []
    for event_log in changes_root.rglob("workflow-events.jsonl"):
        try:
            lines = event_log.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        for line in lines:
            if not line.strip():
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if event.get("event_type") not in allowed_event_types:
                continue
            if _event_covers_artifact_path(event, artifact_path):
                event_errors = _validate_protected_artifact_event(
                    event,
                    artifact_path,
                    expected_change_id=_change_id_for_event_log(event_log),
                    allowed_event_types=allowed_event_types,
                )
                if not event_errors:
                    return []
                matching_errors.extend(event_errors)
    return matching_errors or None


def _validate_protected_artifact_event(
    event: dict,
    artifact_path: str,
    *,
    expected_change_id: str,
    allowed_event_types: tuple[str, ...],
) -> list[str]:
    errors: list[str] = []
    prefix = f"protected artifact event for `{artifact_path}`"
    required_fields = ("reason", "approved_by")

    if event.get("schema") != "workflow-event/v1":
        errors.append(f"{prefix} has invalid schema: {event.get('schema')}")
    if event.get("event_type") not in allowed_event_types:
        errors.append(f"{prefix} has invalid event_type: {event.get('event_type')}")
    if event.get("change_id") != expected_change_id:
        errors.append(f"{prefix} change_id mismatch: {event.get('change_id')}")
    for field in required_fields:
        value = event.get(field)
        if not isinstance(value, str) or _is_placeholder_body(value):
            errors.append(f"{prefix} missing required field: {field}")
    return errors


def _allowed_event_types_for_protected_path(path: str) -> tuple[str, ...] | None:
    for match_type, pattern, event_types in PROTECTED_PATH_RULES:
        if match_type == "exact" and path == pattern:
            return event_types
        if match_type == "prefix" and path.startswith(pattern):
            return event_types
    return None


def _event_covers_artifact_path(event: dict, changed_path: str) -> bool:
    artifact_path = event.get("artifact_path")
    if not isinstance(artifact_path, str):
        return False
    return changed_path == artifact_path or changed_path.startswith(
        artifact_path.rstrip("/") + "/"
    )


def _change_id_for_event_log(event_log: Path) -> str:
    change_dir = event_log.parent
    if change_dir.parent.name == "archive":
        match = re.match(r"\d{4}-\d{2}-\d{2}-(.+)", change_dir.name)
        if match:
            return match.group(1)
    return change_dir.name


def check_change(change_dir: Path, current_specs_root: Path | None = None) -> list[str]:
    errors: list[str] = []
    proposal = change_dir / "proposal.md"
    if not proposal.exists():
        return [f"{change_dir.name}: missing required file: proposal.md"]

    proposal_text = proposal.read_text(encoding="utf-8")
    change_type, type_errors = parse_change_type(proposal_text)
    errors.extend(f"{change_dir.name}: {error}" for error in type_errors)
    if change_type is None:
        return errors

    all_types = change_type.all_types
    if "docs" in all_types and len(all_types) > 1:
        errors.append(f"{change_dir.name}: docs type must not be combined with other types")

    if all_types & DESIGN_TYPES:
        errors.extend(
            f"{change_dir.name}: {error}"
            for error in _check_required_sections(change_dir / "design.md", DESIGN_SECTIONS)
        )

    if change_type.primary != "docs":
        errors.extend(
            f"{change_dir.name}: {error}"
            for error in _check_impact_analysis(change_dir, proposal_text)
        )
        errors.extend(
            f"{change_dir.name}: {error}"
            for error in _check_reference_implementation_research(
                change_dir, proposal_text, change_type
            )
        )

    if all_types & DIAGNOSIS_TYPES:
        errors.extend(
            f"{change_dir.name}: {error}"
            for error in _check_required_sections(
                change_dir / "diagnosis.md", DIAGNOSIS_SECTIONS
            )
        )

    if change_type.primary == "docs" and change_type.secondary:
        errors.append(f"{change_dir.name}: docs primary changes must not declare secondary types")

    errors.extend(
        f"{change_dir.name}: {error}"
        for error in _check_handoff_json(change_dir)
    )

    errors.extend(
        f"{change_dir.name}: {error}"
        for error in _check_review_manifests(change_dir, change_type)
    )

    errors.extend(
        f"{change_dir.name}: {error}"
        for error in _check_design_review_task(change_dir, change_type)
    )

    errors.extend(
        f"{change_dir.name}: {error}"
        for error in _check_benchmark_smoke_task(change_dir, proposal_text)
    )

    errors.extend(
        f"{change_dir.name}: {error}"
        for error in _check_current_spec_mapping(change_dir, current_specs_root)
    )

    errors.extend(
        f"{change_dir.name}: {error}"
        for error in _check_current_spec_sync_task(change_dir, change_type)
    )

    return errors


def iter_change_dirs(changes_root: Path, only_change: str | None) -> list[Path]:
    if only_change:
        return [changes_root / only_change]
    return sorted(
        path
        for path in changes_root.iterdir()
        if path.is_dir() and path.name != "archive" and not path.name.startswith(".")
    )


def _archived_change_names(changes_root: Path) -> set[str]:
    archive_root = changes_root / "archive"
    if not archive_root.exists():
        return set()

    archived: set[str] = set()
    for path in archive_root.iterdir():
        if not path.is_dir():
            continue
        name = path.name
        match = re.match(r"\d{4}-\d{2}-\d{2}-(.+)", name)
        archived.add(match.group(1) if match else name)
    return archived


def _extract_backlog_sections(backlog_text: str) -> tuple[str, str]:
    unfinished_match = re.search(r"^##\s+未实现队列\s*$", backlog_text, flags=re.MULTILINE)
    done_match = re.search(r"^##\s+已完成待归档\s*$", backlog_text, flags=re.MULTILINE)

    unfinished = ""
    done = ""
    if unfinished_match:
        unfinished_start = unfinished_match.end()
        unfinished_end = done_match.start() if done_match else len(backlog_text)
        unfinished = backlog_text[unfinished_start:unfinished_end]
    if done_match:
        done = backlog_text[done_match.end():]
    return unfinished, done


def check_backlog_consistency(changes_root: Path, backlog_path: Path) -> list[str]:
    if not backlog_path.exists():
        return [f"backlog file does not exist: {backlog_path}"]

    active = {
        path.name
        for path in changes_root.iterdir()
        if path.is_dir() and path.name != "archive" and not path.name.startswith(".")
    }
    archived = _archived_change_names(changes_root)
    unfinished_section, done_section = _extract_backlog_sections(
        backlog_path.read_text(encoding="utf-8")
    )
    unfinished = set(BACKLOG_CHANGE_PATTERN.findall(unfinished_section))
    done = set(DONE_BACKLOG_PATTERN.findall(done_section))

    errors: list[str] = []
    for change_id in sorted(unfinished | done):
        if change_id in archived:
            errors.append(
                f"backlog references archived change `{change_id}`; remove it from backlog"
            )
        elif change_id not in active:
            errors.append(
                f"backlog references missing active change `{change_id}`"
            )
    return errors


def _repo_root_for_changes_root(changes_root: Path) -> Path:
    if changes_root.name == "changes" and changes_root.parent.name == "openspec":
        return changes_root.parent.parent
    return Path.cwd()


def _changed_paths_since_base(repo_root: Path, base_ref: str) -> set[str]:
    result = subprocess.run(
        ["git", "diff", "--name-only", base_ref, "--"],
        cwd=repo_root,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return set()
    return {line.strip() for line in result.stdout.splitlines() if line.strip()}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--changes-root", default="openspec/changes")
    parser.add_argument("--current-specs-root", default="openspec/specs")
    parser.add_argument("--change", help="Check a single active change")
    parser.add_argument("--backlog", default="docs/openspec-change-backlog.md")
    parser.add_argument("--base-ref", default="master")
    parser.add_argument(
        "--skip-backlog",
        action="store_true",
        help="Skip backlog/archive consistency checks",
    )
    parser.add_argument(
        "--skip-protected-paths",
        action="store_true",
        help="Skip git diff checks for workflow-protected project artifacts",
    )
    args = parser.parse_args(argv)

    changes_root = Path(args.changes_root)
    if not changes_root.exists():
        print(f"changes root does not exist: {changes_root}", file=sys.stderr)
        return 2

    errors: list[str] = []
    for change_dir in iter_change_dirs(changes_root, args.change):
        if not change_dir.exists():
            errors.append(f"{change_dir.name}: change directory does not exist")
            continue
        errors.extend(check_change(change_dir, Path(args.current_specs_root)))

    if not args.change and not args.skip_backlog:
        errors.extend(check_backlog_consistency(changes_root, Path(args.backlog)))

    if not args.skip_protected_paths:
        repo_root = _repo_root_for_changes_root(changes_root)
        changed_paths = _changed_paths_since_base(repo_root, args.base_ref)
        errors.extend(
            check_protected_path_explanations(repo_root, changed_paths=changed_paths)
        )

    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1

    print("OpenSpec artifact checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
