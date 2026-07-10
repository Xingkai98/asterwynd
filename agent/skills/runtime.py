from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from agent.skills.loader import Skill, SkillDiagnostic, SkillLoadOutcome, SkillLoader


@dataclass(frozen=True)
class SkillActivationResult:
    activated: bool
    message: str
    skill_name: str
    source: str


class SkillRuntime:
    def __init__(
        self,
        skills: list[Skill] | None = None,
        diagnostics: list[SkillDiagnostic] | None = None,
        roots: tuple[Path, ...] = (),
    ):
        self.skills = skills or []
        self.diagnostics = diagnostics or []
        self.roots = roots
        self._skills_by_name = {skill.name.lower(): skill for skill in self.skills}
        self._active_skill_names: set[str] = set()
        self._activations: list[dict[str, str]] = []
        self._queued_activations: list[dict[str, str]] = []
        self._loader = SkillLoader()

    @classmethod
    def from_roots(cls, roots: list[str | Path] | tuple[str | Path, ...]) -> "SkillRuntime":
        expanded_roots = tuple(Path(root).expanduser() for root in roots)
        outcome = SkillLoader().load_roots(expanded_roots)
        return cls(
            skills=outcome.skills,
            diagnostics=outcome.diagnostics,
            roots=expanded_roots,
        )

    def reload(self) -> SkillLoadOutcome:
        outcome = self._loader.load_roots(self.roots)
        self.skills = outcome.skills
        self.diagnostics = outcome.diagnostics
        self._skills_by_name = {skill.name.lower(): skill for skill in self.skills}
        self._active_skill_names = {
            name for name in self._active_skill_names if name in self._skills_by_name
        }
        return outcome

    @property
    def activations(self) -> list[dict[str, str]]:
        return list(self._activations)

    @property
    def active_skill_names(self) -> list[str]:
        return sorted(self._active_skill_names)

    def restore_skills(self, names: list[str]) -> None:
        """恢复已激活 skill 列表，自动过滤当前环境中不存在的 skill。"""
        for name in names:
            canonical = name.strip().lstrip("/").lower()
            if canonical in self._skills_by_name:
                self._active_skill_names.add(canonical)

    def begin_run(self, user_input: str) -> None:
        self._active_skill_names = set()
        self._activations = []
        queued = self._queued_activations
        self._queued_activations = []
        for activation in queued:
            self.activate_skill(
                activation["skill_name"],
                source=activation["source"],
                reason=activation.get("reason"),
            )
        for skill in self.skills:
            if not skill.always and not self._matches_user_input(skill, user_input):
                continue
            source = "always" if skill.always else "local_match"
            self.activate_skill(skill.name, source=source)

    def queue_activation(
        self,
        skill_name: str,
        *,
        source: str,
        reason: str | None = None,
    ) -> SkillActivationResult:
        skill = self.get_skill(skill_name)
        if skill is None:
            return SkillActivationResult(
                activated=False,
                message=f"Unknown skill: {skill_name}",
                skill_name=skill_name,
                source=source,
            )
        self._queued_activations.append(
            {
                "skill_name": skill.name,
                "source": source,
                **({"reason": reason} if reason else {}),
            }
        )
        return SkillActivationResult(
            activated=True,
            message=f"Queued skill: {skill.name}",
            skill_name=skill.name,
            source=source,
        )

    def activate_skill(
        self,
        skill_name: str,
        *,
        source: str,
        reason: str | None = None,
    ) -> SkillActivationResult:
        canonical = skill_name.strip().lstrip("/").lower()
        skill = self._skills_by_name.get(canonical)
        if skill is None:
            return SkillActivationResult(
                activated=False,
                message=f"Unknown skill: {skill_name}",
                skill_name=skill_name,
                source=source,
            )
        if canonical in self._active_skill_names:
            return SkillActivationResult(
                activated=False,
                message=f"Skill already active: {skill.name}",
                skill_name=skill.name,
                source=source,
            )
        self._active_skill_names.add(canonical)
        activation = {"skill_name": skill.name, "source": source}
        if reason:
            activation["reason"] = reason
        self._activations.append(activation)
        return SkillActivationResult(
            activated=True,
            message=f"Activated skill: {skill.name}",
            skill_name=skill.name,
            source=source,
        )

    def get_skill(self, skill_name: str) -> Skill | None:
        return self._skills_by_name.get(skill_name.strip().lstrip("/").lower())

    def render_skill_index(self) -> str:
        invocable = [skill for skill in self.skills if skill.user_invocable]
        if not invocable:
            return ""
        lines = ["Available skills:"]
        for skill in invocable:
            usage = f"/{skill.name} {skill.argument_hint}".rstrip()
            description = f": {skill.description}" if skill.description else ""
            lines.append(f"- {skill.name}{description}. Invoke: {usage}")
        return "\n".join(lines)

    def render_active_skill_context(self) -> str:
        parts = []
        for name in sorted(self._active_skill_names):
            skill = self._skills_by_name.get(name)
            if skill:
                parts.append(f"## Active Skill: {skill.name}\n{skill.prompt}")
        return "\n\n".join(parts)

    def _matches_user_input(self, skill: Skill, user_input: str) -> bool:
        if skill.always:
            return True
        query_lower = user_input.lower()
        candidates = [skill.name, skill.description, *skill.triggers]
        return any(candidate and candidate.lower() in query_lower for candidate in candidates)
