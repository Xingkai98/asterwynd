from pathlib import Path

from scripts.check_openspec_artifacts import check_change, parse_change_type


VALID_DESIGN = """## Context
This change has context.

## Goals / Non-Goals
Goals and non-goals are documented.

## Decisions
Decision one is documented.

## Risks / Trade-offs
Risks are documented.

## Testing Strategy
Tests are documented.
"""

VALID_DIAGNOSIS = """## Symptom
The issue is visible.

## Reproduction
Run the repro.

## Evidence
Evidence is recorded.

## Root Cause
The root cause is known.

## Recommended Direction
The direction is documented.

## Regression Tests
Regression tests are documented.
"""


def write_change(root: Path, proposal: str, design: str | None = None, diagnosis: str | None = None):
    root.mkdir()
    (root / "proposal.md").write_text(proposal, encoding="utf-8")
    if design is not None:
        (root / "design.md").write_text(design, encoding="utf-8")
    if diagnosis is not None:
        (root / "diagnosis.md").write_text(diagnosis, encoding="utf-8")


def test_parse_change_type_primary_and_secondary():
    change_type, errors = parse_change_type(
        """## Change Type

- primary: bugfix
- secondary: [research, feature]
"""
    )

    assert errors == []
    assert change_type is not None
    assert change_type.primary == "bugfix"
    assert change_type.secondary == ("research", "feature")
    assert change_type.all_types == {"bugfix", "research", "feature"}


def test_combined_bugfix_research_feature_requires_diagnosis_and_design(tmp_path):
    change = tmp_path / "harden-web-search"
    write_change(
        change,
        """## Change Type

- primary: bugfix
- secondary: [research, feature]
""",
        design=VALID_DESIGN,
    )

    errors = check_change(change)

    assert errors == ["harden-web-search: missing required file: diagnosis.md"]


def test_combined_type_passes_when_all_required_artifacts_exist(tmp_path):
    change = tmp_path / "harden-web-search"
    write_change(
        change,
        """## Change Type

- primary: bugfix
- secondary: [research, feature]
""",
        design=VALID_DESIGN,
        diagnosis=VALID_DIAGNOSIS,
    )

    assert check_change(change) == []


def test_design_placeholder_section_fails(tmp_path):
    change = tmp_path / "add-feature"
    write_change(
        change,
        """## Change Type

- primary: feature
""",
        design="""## Context
<!-- Background and current state -->

## Goals / Non-Goals
Goals are documented.

## Decisions
Decisions are documented.

## Risks / Trade-offs
Risks are documented.

## Testing Strategy
Tests are documented.
""",
    )

    assert check_change(change) == [
        "add-feature: design.md section is empty or placeholder-only: ## Context"
    ]


def test_docs_only_change_does_not_require_design(tmp_path):
    change = tmp_path / "fix-readme"
    write_change(
        change,
        """## Change Type

- primary: docs
""",
    )

    assert check_change(change) == []
