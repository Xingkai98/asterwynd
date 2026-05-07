# Plan 7: 技能系统

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现 SkillLoader（Markdown 技能动态加载）+ 2个示例技能文件

**Architecture:**
- `Skill` dataclass：元信息 + prompt 片段
- `SkillLoader`：从 .md 文件解析技能，支持 always/按需两种加载模式
- `skills/`：默认技能目录

**Tech Stack:** pathlib, re (frontmatter 解析)

---

## 文件清单

- Create: `agent/skills/loader.py`
- Modify: `agent/skills/__init__.py`
- Create: `skills/code-review.md`
- Create: `skills/research.md`
- Create: `tests/agent/skills/test_loader.py`

---

### Task 1: SkillLoader

- [ ] **Step 1: 创建 tests/agent/skills/test_loader.py，写入测试**

```python
# tests/agent/skills/test_loader.py
import pytest
from pathlib import Path
import tempfile
from agent.skills.loader import Skill, SkillLoader

def test_parse_skill_md():
    content = """---
name: test-skill
description: A test skill
tools: [Read, Bash]
always: false
---

# Test Skill

You are a test assistant.
"""
    with tempfile.NamedTemporaryFile(suffix=".md", mode="w", delete=False) as f:
        f.write(content)
        path = Path(f.name)

    try:
        loader = SkillLoader()
        skill = loader._parse_skill_md(path)
        assert skill.name == "test-skill"
        assert skill.always is False
        assert "You are a test assistant" in skill.prompt
    finally:
        path.unlink()

def test_get_system_prompt():
    loader = SkillLoader()
    skills = [
        Skill(name="s1", description="d1", prompt="p1", tools=[], always=True),
        Skill(name="s2", description="d2", prompt="p2", tools=[], always=False),
    ]
    prompt = loader.get_system_prompt(skills)
    assert "s1" in prompt
    assert "p1" in prompt
    assert "s2" not in prompt  # always=False 不在 system prompt 中

def test_load_skills_from_dir(tmp_path):
    (tmp_path / "skill1.md").write_text("""---
name: skill1
description: desc1
tools: []
always: true
---
# Skill 1
""")
    loader = SkillLoader()
    skills = loader.load(str(tmp_path))
    assert len(skills) == 1
    assert skills[0].name == "skill1"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/agent/skills/test_loader.py -v`
Expected: FAIL — ModuleNotFoundError

- [ ] **Step 3: 创建 agent/skills/loader.py**

```python
# agent/skills/loader.py
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

@dataclass
class Skill:
    """技能元信息"""
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
        """生成 system prompt 片段，包含所有 always=True 的技能"""
        parts = []
        for s in skills:
            if s.always:
                parts.append(f"## Skill: {s.name}\n{s.prompt}")
        return "\n\n".join(parts)

    def match_skills(self, query: str, skills: list[Skill]) -> list[Skill]:
        """简单 string match，按需加载时使用"""
        matched = []
        for s in skills:
            if s.always:
                continue
            if s.description and s.description.lower() in query.lower():
                matched.append(s)
        return matched
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/agent/skills/test_loader.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/agent/skills/test_loader.py agent/skills/loader.py agent/skills/__init__.py
git commit -m "feat: 实现 SkillLoader"
```

---

### Task 2: 示例技能文件

- [ ] **Step 1: 创建 skills/code-review.md**

```markdown
---
name: code-review
description: 执行代码审查，发现潜在 bug
tools: [Read, Bash]
always: false
---

# Code Review Skill

你是一个专业的代码审查专家。当用户要求审查代码时：

1. 先用 Read 工具阅读代码文件
2. 检查常见问题：空指针引用、资源泄漏、安全漏洞、逻辑错误
3. 使用 Bash 执行代码中的测试用例
4. 总结发现的问题，按严重程度分级（高/中/低）
5. 提供具体的修复建议
```

- [ ] **Step 2: 创建 skills/research.md**

```markdown
---
name: research
description: 研究主题，搜集网络信息并总结
tools: [WebSearch, WebFetch]
always: false
---

# Research Skill

你是一个专业的研究助手。当用户要求研究某个主题时：

1. 使用 WebSearch 搜索相关资料（多个关键词）
2. 使用 WebFetch 获取重要页面的完整内容
3. 整理收集到的信息，按主题分类
4. 生成结构化的研究报告，包含：背景、主要观点、不同来源的对比、结论
5. 列出所有参考来源的 URL
```

- [ ] **Step 3: Commit**

```bash
git add skills/code-review.md skills/research.md
git commit -m "feat: 添加 code-review 和 research 示例技能"
```
