#!/usr/bin/env python3
"""Check project-level OpenSpec artifact rules.

This checker intentionally performs mechanical checks only:

- required files exist for the declared change type set
- required sections exist and contain non-placeholder body text
- proposal.md declares Change Type with primary/secondary fields
- change spec delta capabilities map to current specs
- non-docs changes with spec deltas include a current spec sync task
- non-docs changes include Impact Analysis
- changes that require design include a Pre-Implementation Review record

It does not judge whether a design is technically correct. Human review owns
that gate.
"""

from __future__ import annotations

import argparse
import re
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

PLACEHOLDER_ONLY = {
    "todo",
    "tbd",
    "n/a",
    "na",
    "待补充",
    "无",
}


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
    return "grill-with-docs" in lowered or "等价设计追问" in tasks_text


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
            "tasks.md missing pre-implementation grill-with-docs or equivalent design review task"
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--changes-root", default="openspec/changes")
    parser.add_argument("--current-specs-root", default="openspec/specs")
    parser.add_argument("--change", help="Check a single active change")
    parser.add_argument("--backlog", default="docs/openspec-change-backlog.md")
    parser.add_argument(
        "--skip-backlog",
        action="store_true",
        help="Skip backlog/archive consistency checks",
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

    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1

    print("OpenSpec artifact checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
