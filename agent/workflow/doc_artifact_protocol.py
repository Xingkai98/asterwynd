"""Documentation Artifact Protocol — abstract interface for document artifact systems.

Workflow engine calls this protocol at each phase gate to verify that required
document artifacts exist and meet content standards. OpenSpec is the default
implementation; swap by changing ``doc_artifact.protocol`` in
``workflow_methods.json``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class FileRequirement:
    """Declaration of a required file for a phase gate."""

    path_template: str  # e.g. "openspec/changes/{change_id}/proposal.md"
    must_exist: bool = True
    description: str = ""


@dataclass(frozen=True)
class ContentRequirement:
    """Declaration of a content-level check for a phase gate."""

    file_template: str  # e.g. "openspec/changes/{change_id}/proposal.md"
    check_type: str  # e.g. "section_present", "change_type_valid", "spec_delta_sync_completed"
    params: dict = field(default_factory=dict)  # check-specific parameters
    is_blocking: bool = True
    description: str = ""


@dataclass
class ArtifactCheck:
    """A single named check result."""

    name: str
    passed: bool
    detail: str = ""
    is_blocking: bool = True  # blocking failures prevent gate passage


@dataclass
class ArtifactCheckResult:
    """Aggregate result from running all checks for a phase."""

    phase: str
    change_id: str
    checks: list[ArtifactCheck] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        """True if all blocking checks passed."""
        return all(c.passed for c in self.checks if c.is_blocking)

    @property
    def all_passed(self) -> bool:
        """True if every single check (including non-blocking) passed."""
        return all(c.passed for c in self.checks)

    @property
    def errors(self) -> list[str]:
        """Error strings for backward-compat with check_phase_done.py."""
        return [c.detail for c in self.checks if not c.passed and c.is_blocking]


@runtime_checkable
class DocArtifactProtocol(Protocol):
    """Protocol that any document artifact system must implement.

    OpenSpec is the default implementation. To swap in another system,
    implement this protocol and point ``workflow_methods.json`` at it.
    """

    @property
    def name(self) -> str:
        """Human-readable name, e.g. 'OpenSpec'."""
        ...

    @property
    def version(self) -> str:
        """Protocol version for compatibility checks."""
        ...

    def get_required_files(self, phase: str, change_id: str) -> list[FileRequirement]:
        """Return the list of files that must exist at a given phase gate."""
        ...

    def get_content_requirements(
        self, phase: str, change_id: str
    ) -> list[ContentRequirement]:
        """Return the list of content-level checks to run at a given phase gate."""
        ...

    def check_phase_artifacts(
        self,
        phase: str,
        change_id: str,
        change_dir: Path,
        repo_root: Path,
    ) -> ArtifactCheckResult:
        """Run ALL checks for a given phase gate.

        This is the single entry point called by ``check_phase_done.py``.
        Combines file existence verification and content validation.
        """
        ...

    def validate_repo_state(self, repo_root: Path) -> ArtifactCheckResult:
        """Run repo-wide consistency checks (backlog, archive, etc.)."""
        ...
