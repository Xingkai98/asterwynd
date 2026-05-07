# agent/skills/loader.py
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

@dataclass
class Skill:
    name: str
    description: str
    prompt: str
    tools: list[str]
    always: bool = False

class SkillLoader:
    FRONTMATTER_RE = re.compile(
        r"^---\s*\n(.*?)\n---\s*\n(.*)",
        re.DOTALL,
    )

    def load(self, skills_dir: str) -> list[Skill]:
        skills = []
        path = Path(skills_dir)
        if not path.exists():
            return skills
        for f in path.glob("*.md"):
            try:
                skill = self._parse_skill_md(f)
                skills.append(skill)
            except Exception:
                pass
        return skills

    def _parse_skill_md(self, path: Path) -> Skill:
        content = path.read_text(errors="replace")
        match = self.FRONTMATTER_RE.match(content)
        if not match:
            raise ValueError(f"Invalid skill format: {path}")

        frontmatter, body = match.groups()

        name = self._extract_field(frontmatter, "name")
        description = self._extract_field(frontmatter, "description")
        tools_str = self._extract_field(frontmatter, "tools", default="[]")
        always_str = self._extract_field(frontmatter, "always", default="false")

        tools = [t.strip() for t in tools_str.strip("[]").split(",") if t.strip()]

        return Skill(
            name=name or path.stem,
            description=description or "",
            prompt=body.strip(),
            tools=tools,
            always=always_str.lower() == "true",
        )

    def _extract_field(self, frontmatter: str, field: str, default: str = "") -> str:
        pattern = re.compile(f"^{field}:\\s*(.*)$", re.MULTILINE)
        match = pattern.search(frontmatter)
        return match.group(1).strip() if match else default

    def get_system_prompt(self, skills: list[Skill]) -> str:
        parts = []
        for s in skills:
            if s.always:
                parts.append(f"## Skill: {s.name}\n{s.prompt}")
        return "\n\n".join(parts)

    def match_skills(self, query: str, skills: list[Skill]) -> list[Skill]:
        matched = []
        for s in skills:
            if s.always:
                continue
            if s.description and s.description.lower() in query.lower():
                matched.append(s)
        return matched