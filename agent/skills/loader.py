from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class Skill:
    name: str
    description: str
    prompt: str
    tools: list[str]
    always: bool = False
    triggers: tuple[str, ...] = ()
    argument_hint: str = "<request>"
    user_invocable: bool = True
    source_path: Path | None = None
    root: Path | None = None


@dataclass(frozen=True)
class SkillDiagnostic:
    level: str
    message: str
    path: Path | None = None


@dataclass(frozen=True)
class SkillLoadOutcome:
    skills: list[Skill] = field(default_factory=list)
    diagnostics: list[SkillDiagnostic] = field(default_factory=list)


class SkillLoader:
    FRONTMATTER_RE = re.compile(
        r"^---\s*\n(.*?)\n---\s*\n(.*)",
        re.DOTALL,
    )

    def load_roots(self, roots: list[str | Path] | tuple[str | Path, ...]) -> SkillLoadOutcome:
        skills: list[Skill] = []
        diagnostics: list[SkillDiagnostic] = []
        seen: set[str] = set()

        for raw_root in roots:
            root = Path(raw_root).expanduser()
            if not root.exists():
                diagnostics.append(
                    SkillDiagnostic(
                        level="warning",
                        message=f"Skill root does not exist: {root}",
                        path=root,
                    )
                )
                continue
            if not root.is_dir():
                diagnostics.append(
                    SkillDiagnostic(
                        level="warning",
                        message=f"Skill root is not a directory: {root}",
                        path=root,
                    )
                )
                continue

            for skill_file in sorted(root.glob("*/SKILL.md")):
                try:
                    skill = self._parse_skill_md(skill_file, root=root)
                except Exception as exc:
                    diagnostics.append(
                        SkillDiagnostic(
                            level="warning",
                            message=str(exc),
                            path=skill_file,
                        )
                    )
                    continue
                canonical = skill.name.lower()
                if canonical in seen:
                    diagnostics.append(
                        SkillDiagnostic(
                            level="warning",
                            message=f"duplicate skill skipped: {skill.name}",
                            path=skill_file,
                        )
                    )
                    continue
                seen.add(canonical)
                skills.append(skill)

        return SkillLoadOutcome(skills=skills, diagnostics=diagnostics)

    def load(self, skills_dir: str) -> list[Skill]:
        """Backward-compatible wrapper returning only valid directory-style skills."""
        return self.load_roots([skills_dir]).skills

    def _parse_skill_md(self, path: Path, root: Path | None = None) -> Skill:
        content = path.read_text(encoding="utf-8", errors="replace")
        match = self.FRONTMATTER_RE.match(content)
        if not match:
            raise ValueError(f"Invalid skill format: {path}")

        frontmatter_text, body = match.groups()
        frontmatter = yaml.safe_load(frontmatter_text) or {}
        if not isinstance(frontmatter, dict):
            raise ValueError(f"Invalid skill frontmatter: {path}")

        name = _string_field(frontmatter, "name") or path.parent.name
        description = _string_field(frontmatter, "description")
        tools = _string_list_field(frontmatter, "tools")
        always = _bool_field(frontmatter, "always", default=False)
        triggers = tuple(_string_list_field(frontmatter, "triggers"))
        argument_hint = (
            _string_field(frontmatter, "argument_hint")
            or _string_field(frontmatter, "argument-hint")
            or "<request>"
        )
        user_invocable = _bool_field(
            frontmatter,
            "user_invocable",
            default=_bool_field(frontmatter, "user-invocable", default=True),
        )

        return Skill(
            name=name,
            description=description,
            prompt=body.strip(),
            tools=tools,
            always=always,
            triggers=triggers,
            argument_hint=argument_hint,
            user_invocable=user_invocable,
            source_path=path,
            root=root,
        )

    def get_system_prompt(self, skills: list[Skill]) -> str:
        parts = []
        for skill in skills:
            if skill.always:
                parts.append(_format_skill_prompt(skill))
        return "\n\n".join(parts)

    def match_skills(self, query: str, skills: list[Skill]) -> list[Skill]:
        query_lower = query.lower()
        matched = []
        for skill in skills:
            if skill.always:
                continue
            candidates = [skill.name, skill.description, *skill.triggers]
            if any(candidate and candidate.lower() in query_lower for candidate in candidates):
                matched.append(skill)
        return matched


def _format_skill_prompt(skill: Skill) -> str:
    return f"## Active Skill: {skill.name}\n{skill.prompt}"


def _string_field(frontmatter: dict[str, Any], name: str) -> str:
    value = frontmatter.get(name, "")
    if value is None:
        return ""
    if not isinstance(value, str):
        return str(value)
    return value.strip()


def _bool_field(frontmatter: dict[str, Any], name: str, *, default: bool) -> bool:
    value = frontmatter.get(name, default)
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _string_list_field(frontmatter: dict[str, Any], name: str) -> list[str]:
    value = frontmatter.get(name, [])
    if value is None:
        return []
    if isinstance(value, str):
        raw = value.strip()
        if raw.startswith("[") and raw.endswith("]"):
            raw = raw[1:-1]
        return [item.strip().strip("'\"") for item in raw.split(",") if item.strip()]
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value).strip()]
