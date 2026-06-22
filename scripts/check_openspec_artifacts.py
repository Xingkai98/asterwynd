#!/usr/bin/env python3
"""Check project-level OpenSpec artifact rules.

This checker intentionally performs mechanical checks only:

- required files exist for the declared change type set
- required sections exist and contain non-placeholder body text
- proposal.md declares Change Type with primary/secondary fields

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

DESIGN_SECTIONS = [
    "Context",
    "Goals / Non-Goals",
    "Decisions",
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


def check_change(change_dir: Path) -> list[str]:
    errors: list[str] = []
    proposal = change_dir / "proposal.md"
    if not proposal.exists():
        return [f"{change_dir.name}: missing required file: proposal.md"]

    change_type, type_errors = parse_change_type(proposal.read_text(encoding="utf-8"))
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

    if all_types & DIAGNOSIS_TYPES:
        errors.extend(
            f"{change_dir.name}: {error}"
            for error in _check_required_sections(
                change_dir / "diagnosis.md", DIAGNOSIS_SECTIONS
            )
        )

    if change_type.primary == "docs" and change_type.secondary:
        errors.append(f"{change_dir.name}: docs primary changes must not declare secondary types")

    return errors


def iter_change_dirs(changes_root: Path, only_change: str | None) -> list[Path]:
    if only_change:
        return [changes_root / only_change]
    return sorted(
        path
        for path in changes_root.iterdir()
        if path.is_dir() and path.name != "archive" and not path.name.startswith(".")
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--changes-root", default="openspec/changes")
    parser.add_argument("--change", help="Check a single active change")
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
        errors.extend(check_change(change_dir))

    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1

    print("OpenSpec artifact checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
