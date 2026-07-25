"""OpenSpec implementation of DocArtifactProtocol.

Wraps the existing mechanical checks in ``scripts/check_openspec_artifacts.py``
and adds building-phase spec-delta verification that was previously missing.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from agent.workflow.doc_artifact_protocol import (
    ArtifactCheck,
    ArtifactCheckResult,
    ContentRequirement,
    DocArtifactProtocol,
    FileRequirement,
)


class OpenSpecDocArtifactProtocol(DocArtifactProtocol):
    """OpenSpec document artifact system — default implementation."""

    name: str = "OpenSpec"
    version: str = "1.0"

    def __init__(self, paths: dict[str, str] | None = None) -> None:
        self._paths = paths or {}
        self._change_dir_template = self._paths.get(
            "change_dir_template", "openspec/changes/{change_id}"
        )
        self._specs_dir = self._paths.get("specs_dir", "openspec/specs")
        self._backlog_path = self._paths.get(
            "backlog_path", "docs/openspec-change-backlog.md"
        )
        self._handoff_dir = self._paths.get("handoff_dir", ".handoff")

    # ── File requirements per phase ─────────────────────────────────────

    def get_required_files(self, phase: str, change_id: str) -> list[FileRequirement]:
        tmpl = self._change_dir_template
        resolved = tmpl.replace("{change_id}", change_id)
        base = [
            FileRequirement(f"{resolved}/handoff.json", description="Workflow state file"),
        ]

        phase_files: dict[str, list[FileRequirement]] = {
            "wayfinding": [],
            "planning": [
                FileRequirement(f"{resolved}/proposal.md", description="Change proposal"),
                FileRequirement(f"{resolved}/design.md", description="Design document"),
                FileRequirement(f"{resolved}/tasks.md", description="Task breakdown"),
            ],
            "building": [
                FileRequirement(f"{resolved}/tasks.md", description="Task checklist"),
                FileRequirement(
                    f"{self._handoff_dir}/{change_id}/building-review.md",
                    description="Code review report",
                ),
                FileRequirement(
                    f"{self._handoff_dir}/{change_id}/_agent-calls.json",
                    description="Sub-agent call record",
                ),
            ],
            "closing": [
                FileRequirement(
                    f"{self._handoff_dir}/{change_id}/closing-review.md",
                    description="Archive review report",
                ),
            ],
        }

        return base + phase_files.get(phase, [])

    def get_content_requirements(
        self, phase: str, change_id: str
    ) -> list[ContentRequirement]:
        tmpl = self._change_dir_template
        resolved = tmpl.replace("{change_id}", change_id)

        phase_rules: dict[str, list[ContentRequirement]] = {
            "planning": [
                ContentRequirement(
                    f"{resolved}/proposal.md",
                    "section_present",
                    params={"section": "## Change Type"},
                    description="Must declare change type",
                ),
                ContentRequirement(
                    f"{resolved}/proposal.md",
                    "change_type_valid",
                    description="Change type must be one of allowed types",
                ),
                ContentRequirement(
                    f"{resolved}/proposal.md",
                    "impact_analysis_present",
                    description="Impact Analysis must be non-empty (non-docs)",
                ),
                ContentRequirement(
                    f"{resolved}/proposal.md",
                    "reference_research_present",
                    description="Reference Implementation Research must be present (non-docs)",
                ),
                ContentRequirement(
                    f"{resolved}/design.md",
                    "design_sections_complete",
                    description="All design sections present and non-empty",
                ),
                ContentRequirement(
                    f"{resolved}/tasks.md",
                    "design_review_task_present",
                    description="Must include grill-with-docs design review task",
                ),
                ContentRequirement(
                    f"{resolved}/tasks.md",
                    "spec_sync_task_present",
                    description="Must include current spec sync task if spec delta exists",
                ),
            ],
            "building": [
                ContentRequirement(
                    f"{resolved}/tasks.md",
                    "checkboxes_all_checked",
                    description="All task checkboxes must be [x]",
                ),
                ContentRequirement(
                    f"{resolved}/tasks.md",
                    "spec_delta_sync_completed",
                    description="Spec delta sync task must be [x] if spec deltas exist",
                ),
                ContentRequirement(
                    f"{resolved}/specs",
                    "spec_delta_applied_to_current",
                    description="Delta spec requirements must be present in current specs",
                ),
                ContentRequirement(
                    f"{self._handoff_dir}/{change_id}/building-review.md",
                    "verdict_not_blocked",
                    description="Review must not be BLOCKED or CHANGES_REQUESTED",
                ),
                ContentRequirement(
                    f"{self._handoff_dir}/{change_id}/building-review.md",
                    "tasks_verification_present",
                    description="Must contain ## Tasks Verification section",
                ),
            ],
            "closing": [
                ContentRequirement(
                    "-",
                    "openspec_validate_strict",
                    description="openspec validate --all --strict must pass",
                ),
                ContentRequirement(
                    "-",
                    "change_archived",
                    description="Change must be archived to archive/YYYY-MM-DD-id/",
                ),
                ContentRequirement(
                    "-",
                    "backlog_consistent",
                    description="Backlog must not reference archived or missing changes",
                ),
            ],
        }

        return phase_rules.get(phase, [])

    # ── Main entry point called by check_phase_done.py ─────────────────

    def check_phase_artifacts(
        self,
        phase: str,
        change_id: str,
        change_dir: Path,
        repo_root: Path,
    ) -> ArtifactCheckResult:
        result = ArtifactCheckResult(phase=phase, change_id=change_id)

        # 1. File existence checks
        for req in self.get_required_files(phase, change_id):
            resolved = repo_root / req.path_template
            if req.must_exist and not resolved.exists():
                result.checks.append(
                    ArtifactCheck(
                        name=f"file_exists:{req.path_template}",
                        passed=False,
                        detail=f"Missing required file: {req.path_template} — {req.description}",
                        is_blocking=True,
                    )
                )
            else:
                result.checks.append(
                    ArtifactCheck(
                        name=f"file_exists:{req.path_template}",
                        passed=True,
                        detail=req.description,
                        is_blocking=False,
                    )
                )

        # 2. Phase-specific content checks (delegate to helper methods)
        spec_root = repo_root / self._specs_dir

        if phase == "planning":
            result.checks.extend(self._check_planning_content(change_dir, spec_root))
        elif phase == "building":
            result.checks.extend(
                self._check_building_content(change_id, change_dir, spec_root, repo_root)
            )
        elif phase == "closing":
            result.checks.extend(
                self._check_closing_content(change_id, change_dir, spec_root, repo_root)
            )
        elif phase == "wayfinding":
            result.checks.extend(self._check_wayfinding_content(change_dir))

        return result

    def validate_repo_state(self, repo_root: Path) -> ArtifactCheckResult:
        result = ArtifactCheckResult(phase="repo", change_id="*")
        changes_root = repo_root / self._change_dir_template.split("/{")[0]
        backlog = repo_root / self._backlog_path

        try:
            from scripts.check_openspec_artifacts import check_backlog_consistency

            errors = check_backlog_consistency(changes_root, backlog)
            for err in errors:
                result.checks.append(
                    ArtifactCheck(
                        name="backlog_consistency",
                        passed=False,
                        detail=err,
                        is_blocking=True,
                    )
                )
        except ImportError:
            result.checks.append(
                ArtifactCheck(
                    name="backlog_consistency",
                    passed=False,
                    detail="SKIP: cannot import check_openspec_artifacts",
                    is_blocking=False,
                )
            )

        if not result.checks:
            result.checks.append(
                ArtifactCheck(
                    name="backlog_consistency",
                    passed=True,
                    detail="Backlog is consistent",
                    is_blocking=False,
                )
            )
        return result

    # ── Phase-specific check helpers ───────────────────────────────────

    def _check_wayfinding_content(self, change_dir: Path) -> list[ArtifactCheck]:
        checks: list[ArtifactCheck] = []
        handoff_path = change_dir / "handoff.json"

        if not handoff_path.exists():
            checks.append(
                ArtifactCheck(
                    name="wayfinding_handoff",
                    passed=False,
                    detail="handoff.json does not exist",
                )
            )
            return checks

        try:
            data = json.loads(handoff_path.read_text(encoding="utf-8"))
            state = data.get("state", {})
            sub_state = state.get("sub_state", "")
            transitions = data.get("transitions", [])

            if sub_state in ("map_cleared", "ready_for_review") and not transitions:
                checks.append(
                    ArtifactCheck(
                        name="wayfinding_transitions",
                        passed=False,
                        detail="transitions is empty — wayfinding appears to have made no progress",
                    )
                )
            else:
                checks.append(
                    ArtifactCheck(
                        name="wayfinding_transitions",
                        passed=True,
                        detail=f"Wayfinding has {len(transitions)} transition(s)",
                        is_blocking=False,
                    )
                )
        except Exception as e:
            checks.append(
                ArtifactCheck(
                    name="wayfinding_handoff",
                    passed=False,
                    detail=f"Error reading handoff.json: {e}",
                )
            )

        return checks

    def _check_planning_content(
        self, change_dir: Path, spec_root: Path
    ) -> list[ArtifactCheck]:
        checks: list[ArtifactCheck] = []

        try:
            from scripts.check_openspec_artifacts import check_change

            errors = check_change(change_dir, spec_root)
            for err in errors:
                checks.append(
                    ArtifactCheck(
                        name="planning_artifact",
                        passed=False,
                        detail=err,
                    )
                )
        except ImportError:
            checks.append(
                ArtifactCheck(
                    name="planning_artifact",
                    passed=False,
                    detail="SKIP: cannot import check_openspec_artifacts",
                    is_blocking=False,
                )
            )

        if not checks:
            checks.append(
                ArtifactCheck(
                    name="planning_artifact",
                    passed=True,
                    detail="All planning artifacts pass",
                    is_blocking=False,
                )
            )
        return checks

    def _check_building_content(
        self,
        change_id: str,
        change_dir: Path,
        spec_root: Path,
        repo_root: Path,
    ) -> list[ArtifactCheck]:
        checks: list[ArtifactCheck] = []

        # 1. Task checkboxes all checked
        tasks_path = change_dir / "tasks.md"
        if tasks_path.exists():
            task_text = tasks_path.read_text(encoding="utf-8")
            total = task_text.count("- [ ]") + task_text.count("- [x]")
            done = task_text.count("- [x]")
            if total > 0 and done < total:
                checks.append(
                    ArtifactCheck(
                        name="tasks_checkboxes",
                        passed=False,
                        detail=f"Tasks not all checked: {done}/{total} ({done/total:.0%})",
                    )
                )
            else:
                checks.append(
                    ArtifactCheck(
                        name="tasks_checkboxes",
                        passed=True,
                        detail=f"All {done} task checkboxes are [x]",
                        is_blocking=False,
                    )
                )

        # 2. Spec delta sync completed (NEW — fixes the building gate gap)
        checks.extend(self._check_spec_delta_sync_completed(change_dir))

        # 3. Spec delta applied to current specs (NEW)
        checks.extend(self._check_spec_delta_applied_to_current(change_dir, spec_root))

        # 4. Review report
        review_path = repo_root / self._handoff_dir / change_id / "building-review.md"
        if review_path.exists():
            text = review_path.read_text(encoding="utf-8")
            if "BLOCKED" in text:
                checks.append(
                    ArtifactCheck(
                        name="review_not_blocked",
                        passed=False,
                        detail="Review report contains BLOCKED — unresolved blocking items",
                    )
                )
            elif "CHANGES_REQUESTED" in text:
                checks.append(
                    ArtifactCheck(
                        name="review_not_blocked",
                        passed=False,
                        detail="Review report contains CHANGES_REQUESTED — please resolve all requests",
                    )
                )
            else:
                checks.append(
                    ArtifactCheck(
                        name="review_not_blocked",
                        passed=True,
                        detail="Review report has no blockers",
                        is_blocking=False,
                    )
                )

            # Tasks verification section
            if "## Tasks Verification" in text:
                checks.append(
                    ArtifactCheck(
                        name="tasks_verification",
                        passed=True,
                        detail="Tasks Verification section present",
                        is_blocking=False,
                    )
                )
            else:
                task_text_check = ""
                if tasks_path.exists():
                    task_text_check = tasks_path.read_text(encoding="utf-8")
                has_checkboxes = "- [x]" in task_text_check or "- [ ]" in task_text_check
                if has_checkboxes:
                    checks.append(
                        ArtifactCheck(
                            name="tasks_verification",
                            passed=False,
                            detail="Review report missing ## Tasks Verification section",
                        )
                    )

            # Task group count vs verified count
            if tasks_path.exists():
                task_text_v = tasks_path.read_text(encoding="utf-8")
                task_groups = len(re.findall(r"^### T\d", task_text_v, re.MULTILINE))
                verified_rows = len(re.findall(r"^\| T\d", text, re.MULTILINE))
                if task_groups > 0 and verified_rows < task_groups:
                    checks.append(
                        ArtifactCheck(
                            name="tasks_verification_complete",
                            passed=False,
                            detail=(
                                f"Tasks verification incomplete: {task_groups} task groups "
                                f"but only {verified_rows} verified in review"
                            ),
                        )
                    )
                elif task_groups > 0:
                    checks.append(
                        ArtifactCheck(
                            name="tasks_verification_complete",
                            passed=True,
                            detail=f"All {task_groups} task groups verified",
                            is_blocking=False,
                        )
                    )
        else:
            checks.append(
                ArtifactCheck(
                    name="review_report",
                    passed=False,
                    detail=f"Building review report missing: {review_path}",
                )
            )

        return checks

    def _check_spec_delta_sync_completed(self, change_dir: Path) -> list[ArtifactCheck]:
        """Verify that if spec deltas exist, the sync task in tasks.md is [x].

        At building gate, we check: any task line referencing 'openspec/specs'
        must be checked [x] — the specific keyword check ('current spec'/'当前规格')
        is a planning-gate concern handled by check_openspec_artifacts.
        """
        specs_dir = change_dir / "specs"
        if not specs_dir.exists() or not list(specs_dir.glob("*/spec.md")):
            return []  # No spec deltas — nothing to check

        tasks_path = change_dir / "tasks.md"
        if not tasks_path.exists():
            return [
                ArtifactCheck(
                    name="spec_delta_sync_completed",
                    passed=False,
                    detail="Spec deltas exist but tasks.md is missing — cannot verify sync task",
                )
            ]

        task_text = tasks_path.read_text(encoding="utf-8")

        # Find any checkbox line mentioning openspec/specs
        found_spec_ref = False
        for line in task_text.splitlines():
            stripped = line.strip()
            if "openspec/specs" not in stripped.lower():
                continue
            found_spec_ref = True
            if stripped.startswith("- [x]"):
                return [
                    ArtifactCheck(
                        name="spec_delta_sync_completed",
                        passed=True,
                        detail=f"Spec sync task is [x]: {stripped[:80]}",
                        is_blocking=False,
                    )
                ]
            if stripped.startswith("- [ ]"):
                return [
                    ArtifactCheck(
                        name="spec_delta_sync_completed",
                        passed=False,
                        detail=f"Spec sync task is NOT checked: {stripped}",
                    )
                ]

        if found_spec_ref:
            # Task mentions openspec/specs but not as a checkbox — warn, don't block
            return [
                ArtifactCheck(
                    name="spec_delta_sync_completed",
                    passed=True,
                    detail="Spec sync references found (non-checkbox format)",
                    is_blocking=False,
                )
            ]

        # No reference to openspec/specs at all — spec deltas exist but no sync task
        return [
            ArtifactCheck(
                name="spec_delta_sync_completed",
                passed=False,
                detail=(
                    "Spec deltas exist but tasks.md has no task referencing 'openspec/specs'. "
                    "Add a spec sync task (e.g. '- [x] sync to openspec/specs/...') and check it."
                ),
            )
        ]

    def _check_spec_delta_applied_to_current(
        self, change_dir: Path, spec_root: Path
    ) -> list[ArtifactCheck]:
        """Verify delta spec requirements are present in current specs."""
        specs_dir = change_dir / "specs"
        if not specs_dir.exists():
            return []

        checks: list[ArtifactCheck] = []
        for delta_spec in sorted(specs_dir.glob("*/spec.md")):
            if not delta_spec.is_file():
                continue
            capability = delta_spec.parent.name
            current_spec = spec_root / capability / "spec.md"

            if not current_spec.exists():
                checks.append(
                    ArtifactCheck(
                        name=f"spec_delta_applied:{capability}",
                        passed=False,
                        detail=(
                            f"Delta spec for '{capability}' has no matching current spec "
                            f"at {current_spec}"
                        ),
                    )
                )
                continue

            # Structural check: does the delta have ADDED/MODIFIED/REMOVED sections?
            delta_text = delta_spec.read_text(encoding="utf-8")
            current_text = current_spec.read_text(encoding="utf-8")

            has_delta_content = any(
                marker in delta_text for marker in ("## ADDED", "## MODIFIED", "## REMOVED")
            )
            if not has_delta_content:
                # No explicit requirements — nothing to verify
                continue

            # Check each ADDED requirement exists in current spec
            missing = self._find_unapplied_requirements(delta_text, current_text)
            if missing:
                checks.append(
                    ArtifactCheck(
                        name=f"spec_delta_applied:{capability}",
                        passed=False,
                        detail=(
                            f"Spec delta for '{capability}' has requirements not found in "
                            f"current spec: {', '.join(missing[:5])}"
                        ),
                    )
                )
            else:
                checks.append(
                    ArtifactCheck(
                        name=f"spec_delta_applied:{capability}",
                        passed=True,
                        detail=f"Delta requirements for '{capability}' are present in current spec",
                        is_blocking=False,
                    )
                )

        return checks

    @staticmethod
    def _find_unapplied_requirements(delta_text: str, current_text: str) -> list[str]:
        """Find ADDED/MODIFIED requirement titles in delta that are missing from current."""
        # Extract requirement titles from ADDED and MODIFIED sections in delta
        delta_titles: set[str] = set()
        in_section = False
        for line in delta_text.splitlines():
            stripped = line.strip()
            if stripped.startswith("## ADDED") or stripped.startswith("## MODIFIED"):
                in_section = True
                continue
            if stripped.startswith("## ") and not stripped.startswith("### "):
                in_section = False
                continue
            if in_section and stripped.startswith("### Requirement:"):
                title = stripped[len("### Requirement:"):].strip()
                delta_titles.add(title)

        if not delta_titles:
            return []

        # Check which titles are missing from current spec
        missing: list[str] = []
        for title in sorted(delta_titles):
            if title not in current_text:
                missing.append(title)
        return missing

    def _check_closing_content(
        self,
        change_id: str,
        change_dir: Path,
        spec_root: Path,
        repo_root: Path,
    ) -> list[ArtifactCheck]:
        checks: list[ArtifactCheck] = []

        # 1. Check archived
        changes_root = repo_root / self._change_dir_template.split("/{")[0]
        archive_dir = changes_root / "archive"
        archive_matches = list(archive_dir.glob(f"*{change_id}*"))
        if archive_matches:
            checks.append(
                ArtifactCheck(
                    name="change_archived",
                    passed=True,
                    detail=f"Change 已归档: {archive_matches[0]}",
                    is_blocking=False,
                )
            )
            # Run artifact checker on archived path
            try:
                from scripts.check_openspec_artifacts import check_change

                errors = check_change(archive_matches[0], spec_root)
                for err in errors:
                    checks.append(
                        ArtifactCheck(
                            name="closing_artifact",
                            passed=False,
                            detail=err,
                        )
                    )
            except ImportError:
                pass
        else:
            checks.append(
                ArtifactCheck(
                    name="change_archived",
                    passed=False,
                    detail=f"Change 未归档: 找不到 archive/*{change_id}*",
                )
            )

        # 2. Backlog consistency
        try:
            from scripts.check_openspec_artifacts import check_backlog_consistency

            backlog_path = repo_root / self._backlog_path
            errors = check_backlog_consistency(changes_root, backlog_path)
            for err in errors:
                checks.append(
                    ArtifactCheck(
                        name="backlog_consistency",
                        passed=False,
                        detail=err,
                    )
                )
        except ImportError:
            pass
        if not any(c.name == "backlog_consistency" for c in checks):
            checks.append(
                ArtifactCheck(
                    name="backlog_consistency",
                    passed=True,
                    detail="Backlog is consistent",
                    is_blocking=False,
                )
            )

        # 3. Review report
        review_path = repo_root / self._handoff_dir / change_id / "closing-review.md"
        if review_path.exists():
            checks.append(
                ArtifactCheck(
                    name="closing_review",
                    passed=True,
                    detail="Closing review report exists",
                    is_blocking=False,
                )
            )
        else:
            checks.append(
                ArtifactCheck(
                    name="closing_review",
                    passed=False,
                    detail=f"Closing review report missing: {review_path}",
                )
            )

        return checks
