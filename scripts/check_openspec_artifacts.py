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
    "research_tier",
    "status",
    "reason",
    "research questions",
    "findings",
    "design impact",
)
RESEARCH_TIER_VALUES = ("full", "light", "exempt")
# exempt 结构性豁免关键词（D3 + Q3 确认：不扩展证据路径清单，判断性豁免示例
# 「与已有模块 X 等价改造」类必须带引用才通过）。「方案已由.*决策」用正则，
# 其余子串匹配；证据 = issue 引用 #<数字> 或评审文档路径
# （docs/、openspec/changes/archive/、reviews/）。
STRUCTURAL_EXEMPTION_KEYWORDS = (
    "docs-only",
    "bugfix",
    "上游决策锁定",
    "无设计决策",
)
STRUCTURAL_EXEMPTION_RE_PATTERNS = (re.compile(r"方案已由.*决策"),)
EXEMPT_EVIDENCE_PATH_PATTERNS = ("docs/", "openspec/changes/archive/", "reviews/")
# 内容门槛（#123 阶段感知）：tasks 全勾（实现完成）时命中即红的「自认未完成」
# 短语级模式（grill Q6 确认，删 暂无/未完成 避免误伤「暂无参考仓库可用」类
# 合法 finding）；语义化占位漏检记 docs/known-debt.md，不无限扩表。
SELF_ADMITTED_INCOMPLETE_PHRASES = (
    "尚未完成",
    "待补充",
    "待调研",
    "tbd",
    "todo",
    "待确认",
)


def _self_admitted_incomplete(text: str) -> str | None:
    lowered = text.lower()
    for phrase in SELF_ADMITTED_INCOMPLETE_PHRASES:
        if phrase.lower() in lowered:
            return phrase
    return None

PLACEHOLDER_ONLY = {
    "todo",
    "tbd",
    "n/a",
    "na",
    "待补充",
    "无",
}
# grill-design.md ## User Confirmation 节的"未确认"标记：`用户答复：` 后跟这些
# 值（小写归一后）的确认记录不得计入已确认。与 PLACEHOLDER_ONLY 区分——占位
# 判定是给整节正文用的，这些 token 用于识别"写了占位但没真拍板"的确认行
# （grill-confirmation-gate Q1：占位文本会假通过朴素判定）。
# 占位判定的关键：占位文本短且无实质决策内容；真实答复即使是"排除未确认 token"
# 这类长句也不得误伤。因此短答复（≤20 字符）才做子串匹配，长答复一律视为实质
# 内容。EXACT 精确匹配兜底短占位。
UNCONFIRMED_EXACT = {
    "todo", "tbd", "n/a", "na", "无", "none",
    "待确认", "未确认", "待定", "pending", "待补充", "占位", "未决",
}
UNCONFIRMED_STRONG = {
    "待主 agent", "待主agent", "待用户", "placeholder", "tobeconfirmed",
    "待拍板", "未拍板",
}
_UNCONFIRMED_MAX_ANSWER_LEN = 20
# 标点/空白变体剥离：`待确认。` → `待确认`，`待主agent提交` → `待主agent提交`
_UNCONFIRMED_STRIP = str.maketrans("", "", "。．.；;，,、 \t")


def _is_unconfirmed_answer(answer: str) -> bool:
    """True when an answer value is an unconfirmed marker, not a real decision."""
    a = answer.lower().strip().translate(_UNCONFIRMED_STRIP)
    if not a:
        return True
    if a in UNCONFIRMED_EXACT:
        return True
    # Short answers that merely gesture at "pending" are placeholders; long
    # answers are substantive even if they mention a token like 未确认.
    if len(a) <= _UNCONFIRMED_MAX_ANSWER_LEN:
        for tok in UNCONFIRMED_STRONG:
            if tok in a:
                return True
    return False
PROTECTED_ARTIFACT_EVENT = "protected_artifact_explained"
CURRENT_SPEC_SYNC_EVENT = "current_spec_synced"
BACKLOG_UPDATED_EVENT = "backlog_updated"
CHANGE_ARCHIVED_EVENT = "change_archived"

# 受保护路径规则从 scripts/flow-policy.json 加载（flow-policy-source P0 单一策略源），
# 替换原硬编码 PROTECTED_PATH_RULES。取 governance == event_explained 的条目。
_POLICY_REL_PATH = Path("scripts") / "flow-policy.json"


def _load_protected_path_rules(repo_root: Path) -> tuple[tuple[str, str, tuple[str, ...]], ...] | None:
    """Load event_explained rules from scripts/flow-policy.json.

    Returns None when the policy file is missing/corrupt (fail-closed: the CI
    gate must not silently skip protected-path checks). Raises RuntimeError on
    an event_explained rule without event_types (invalid policy schema).
    """
    policy = repo_root / _POLICY_REL_PATH
    try:
        data = json.loads(policy.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError):
        return None
    if not isinstance(data, dict):
        return None
    rules = data.get("protected_paths")
    if not isinstance(rules, list):
        return None
    out: list[tuple[str, str, tuple[str, ...]]] = []
    for rule in rules:
        if not isinstance(rule, dict) or rule.get("governance") != "event_explained":
            continue
        path = rule.get("path")
        mt = rule.get("match_type")
        et = rule.get("event_types")
        if not isinstance(path, str) or not path:
            continue
        if mt not in ("exact", "prefix", "contains"):
            continue
        if not isinstance(et, (list, tuple)) or not et:
            raise RuntimeError(
                f"scripts/flow-policy.json: event_explained rule for '{path}' "
                "missing event_types (invalid policy schema)"
            )
        out.append((mt, path, tuple(et)))
    return tuple(out)


ALLOWED_POLICY_PHASES = {"wayfinding", "planning", "building", "closing"}
_POLICY_META_KEYS = {"_description"}


def _validate_agent_content(prefix: str, agent: object) -> list[str]:
    """Validate a direct ``{provider, model}`` agent content (#127 P0 schema)."""
    errors: list[str] = []
    if agent is None:
        return errors
    if not isinstance(agent, dict):
        return [f"flow-policy.json `{prefix}` must be an object"]
    if not agent:
        return errors
    for k in ("provider", "model"):
        if k not in agent:
            errors.append(f"flow-policy.json `{prefix}` missing `{k}`")
        elif not isinstance(agent[k], str) or not agent[k]:
            errors.append(f"flow-policy.json `{prefix}.{k}` must be a non-empty string")
    extra = set(agent.keys()) - {"provider", "model"}
    if extra:
        errors.append(
            f"flow-policy.json `{prefix}` has unknown keys: " + ", ".join(sorted(extra))
        )
    return errors


def _validate_agent_decl(prefix: str, val: object) -> list[str]:
    """Validate a ``{agent: {provider, model}}`` phase declaration (#127 P0 schema).

    Accepts an empty dict (schema placeholder) or a ``{agent: {...}}`` wrapper;
    a bare ``{provider, model}`` (direct agent content) is also accepted for
    symmetry with ``review.agent``.
    """
    errors: list[str] = []
    if val is None:
        return errors
    if not isinstance(val, dict):
        return [f"flow-policy.json `{prefix}` must be an object"]
    if not val:
        return errors
    non_meta = set(val.keys()) - _POLICY_META_KEYS
    if "agent" not in val:
        # bare {provider, model} direct content form (review.agent style)
        if non_meta <= {"provider", "model"}:
            return _validate_agent_content(prefix, val)
        errors.append(
            f"flow-policy.json `{prefix}` has unknown keys (expected `agent`): "
            + ", ".join(sorted(non_meta))
        )
        return errors
    if len(non_meta) > 1:
        errors.append(
            f"flow-policy.json `{prefix}` has unknown extra keys: "
            + ", ".join(sorted(non_meta - {"agent"}))
        )
    return _validate_agent_content(f"{prefix}.agent", val.get("agent"))


def _validate_policy_agent_schema(repo_root: Path) -> list[str]:
    """Validate the phases/review agent schema of flow-policy.json (#127 P0).

    Missing/corrupt policy is left to ``_load_protected_path_rules`` fail-closed;
    here we only structurally validate the optional phases/review sections.
    """
    errors: list[str] = []
    policy = repo_root / _POLICY_REL_PATH
    try:
        data = json.loads(policy.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return errors
    if not isinstance(data, dict):
        return errors

    phases = data.get("phases")
    if phases is not None and not isinstance(phases, dict):
        errors.append("flow-policy.json `phases` must be an object")
    elif isinstance(phases, dict):
        for key, val in phases.items():
            if key in _POLICY_META_KEYS:
                continue
            if key not in ALLOWED_POLICY_PHASES:
                errors.append(
                    f"flow-policy.json unknown phase `{key}` "
                    f"(allowed: {', '.join(sorted(ALLOWED_POLICY_PHASES))})"
                )
                continue
            errors.extend(_validate_agent_decl(f"phases.{key}", val))

    review = data.get("review")
    if review is not None and not isinstance(review, dict):
        errors.append("flow-policy.json `review` must be an object")
    elif isinstance(review, dict):
        for key, val in review.items():
            if key in _POLICY_META_KEYS:
                continue
            if key != "agent":
                errors.append(f"flow-policy.json unknown review key `{key}` (allowed: agent)")
                continue
            errors.extend(_validate_agent_decl("review.agent", val))
    return errors


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


def _inside_fence(text: str, pos: int) -> bool:
    """True when ``pos`` falls inside a fenced code block (``` ... ```)."""
    fences = [m.start() for m in re.finditer(r"^```", text, flags=re.MULTILINE)]
    open_fence = None
    for f in fences:
        if f >= pos:
            break
        open_fence = None if open_fence is not None else f
    return open_fence is not None


def _extract_h2_sections(text: str) -> dict[str, str]:
    matches = list(re.finditer(r"^##\s+(.+?)\s*$", text, flags=re.MULTILINE))
    sections: dict[str, str] = {}
    for index, match in enumerate(matches):
        # Skip ## inside fenced code blocks (flow-policy-source P0 正则修复，
        # 与 workflow_guard._h2_section 同步).
        if _inside_fence(text, match.start()):
            continue
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


def _exempt_reason_satisfies(reason: str) -> bool:
    """True when an exempt reason hits a structural keyword or cites evidence.

    判断性豁免必须带客观依据（Q3 口径）：结构性豁免关键词、`#<数字>` issue 引用、
    或评审文档路径（docs/、openspec/changes/archive/、reviews/）。「与已有模块 X
    等价改造」类无引用表述不通过。
    """
    lowered = reason.lower()
    if any(keyword.lower() in lowered for keyword in STRUCTURAL_EXEMPTION_KEYWORDS):
        return True
    if any(pattern.search(reason) for pattern in STRUCTURAL_EXEMPTION_RE_PATTERNS):
        return True
    if re.search(r"#\d+", reason):
        return True
    return any(path in lowered for path in EXEMPT_EVIDENCE_PATH_PATTERNS)


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

    errors: list[str] = []

    # research_tier（结构门槛，proposal 阶段即生效）：必填枚举 full|light|exempt。
    normalized_tier: str | None = None
    tier = _extract_record_field(body, "research_tier")
    if tier is None or _is_placeholder_body(tier):
        errors.append(
            f"{source} section must declare `research_tier: full|light|exempt`: "
            f"## {REFERENCE_RESEARCH_SECTION}"
        )
    else:
        normalized_tier = tier.splitlines()[0].strip().lower()
        if normalized_tier not in RESEARCH_TIER_VALUES:
            errors.append(
                f"{source} section has invalid research_tier `{normalized_tier}` "
                f"(allowed: full, light, exempt)"
            )
            normalized_tier = None

    status = _extract_record_field(body, "status")
    if status is None or _is_placeholder_body(status):
        errors.append(
            f"{source} section must declare `status: enabled` or "
            f"`status: disabled`: ## {REFERENCE_RESEARCH_SECTION}"
        )
        return errors

    normalized_status = status.splitlines()[0].strip().lower()
    if normalized_status not in {"enabled", "disabled"}:
        errors.append(
            f"{source} section has invalid reference implementation research "
            f"status `{normalized_status}` (allowed: enabled, disabled)"
        )
        return errors

    reason = _extract_record_field(body, "reason")
    if reason is None or _is_placeholder_body(reason):
        errors.append(
            f"{source} section must include non-empty `reason`: "
            f"## {REFERENCE_RESEARCH_SECTION}"
        )

    if normalized_status == "enabled":
        # light 档可省略 research questions（D2 + spec「Routine enhancement
        # requires light research」），findings 与 design impact 仍必填。
        enabled_fields = ("research questions", "findings", "design impact")
        if normalized_tier == "light":
            enabled_fields = ("findings", "design impact")
        for field in enabled_fields:
            value = _extract_record_field(body, field)
            if value is None or _is_placeholder_body(value):
                errors.append(
                    f"{source} section must include non-empty `{field}` when "
                    f"reference implementation research is enabled: "
                    f"## {REFERENCE_RESEARCH_SECTION}"
                )

    # 内容门槛（#123 阶段感知）：仅当 tasks 全勾（实现完成）时生效。proposal
    # 阶段只查结构门槛（上述 section 存在 + 非空），不触发内容门槛，避免在途
    # change 被误伤。命中「自认未完成」短语 → exit 2，错误指明短语 + 字段。
    if _tasks_all_complete(change_dir):
        content_fields = ("reason",)
        if normalized_status == "enabled":
            content_fields += ("research questions", "findings", "design impact")
        for field in content_fields:
            value = _extract_record_field(body, field)
            if not value:
                continue
            hit = _self_admitted_incomplete(value)
            if hit:
                errors.append(
                    f"{source} ## {REFERENCE_RESEARCH_SECTION} 的 `{field}` 命中"
                    f"「自认未完成」短语「{hit}」——tasks 已全勾，内容门槛拒绝占位"
                )

        # tier 内容门槛（D4 + Q4 确认）：tasks 全勾时 tier 与 status/证据组合闭环。
        if normalized_tier in ("full", "light"):
            if normalized_status == "disabled":
                errors.append(
                    f"{source} ## {REFERENCE_RESEARCH_SECTION} 的 "
                    f"`research_tier: {normalized_tier}` 在 tasks 已全勾时 "
                    f"`status` 不得为 `disabled`——必调研档必须已完成调研（完成时闭环）"
                )
        elif normalized_tier == "exempt":
            if normalized_status != "disabled":
                errors.append(
                    f"{source} ## {REFERENCE_RESEARCH_SECTION} 的 "
                    f"`research_tier: exempt` 在 tasks 已全勾时 `status` 必须为 "
                    f"`disabled`——做了调研就如实改 full/light + enabled（Q4 口径）"
                )
            if reason and not _is_placeholder_body(reason):
                hit = _self_admitted_incomplete(reason)
                if hit:
                    # #123 内容门槛已报占位短语，这里不重复报
                    pass
                elif not _exempt_reason_satisfies(reason):
                    errors.append(
                        f"{source} ## {REFERENCE_RESEARCH_SECTION} 的 `reason` "
                        f"未命中结构性豁免关键词（docs-only/bugfix/上游决策锁定/"
                        f"无设计决策/方案已由.*决策）也未引用证据（#<数字> 或 "
                        f"docs/、openspec/changes/archive/、reviews/ 路径），"
                        f"exempt 证据校验不通过——请引用已关闭决策 issue 或评审文档路径"
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

    # Structured grill evidence (issue #95 + grill-confirmation-gate):
    # reviews/grill-design.md must exist with a non-empty ## Confirmed Decisions
    # section (>= 3 decision entries), and every ## Open Questions entry must
    # have a matching ## User Confirmation record once the change is complete
    # (tasks all checked). This replaces the literal "batch-grill" string check.
    grill_evidence = change_dir / "reviews" / "grill-design.md"
    if grill_evidence.exists():
        text = grill_evidence.read_text(encoding="utf-8")
        errors: list[str] = []
        decisions = _extract_grill_decisions(text)
        if len(decisions) < 3:
            errors.append(
                f"reviews/grill-design.md 的 ## Confirmed Decisions 不足 3 条"
                f"（当前 {len(decisions)} 条）——独立 subagent design grilling 未完成"
            )
        # User Confirmation coverage (grill-confirmation-gate): only enforced
        # on a completed change (tasks all checked). In-flight changes may keep
        # open questions while the user clarifies mid-development.
        if _tasks_all_complete(change_dir):
            missing = _unconfirmed_open_questions(text)
            if missing:
                errors.append(
                    "reviews/grill-design.md 存在未确认的 Open Question: "
                    + ", ".join(missing)
                    + " ——每个 Open Question 必须有 ## User Confirmation 记录，未确认不允许归档"
                )
        return errors

    # A *completed* change (non-docs, tasks all checked) must show structured
    # grill evidence — the literal marker is no longer enough once the change
    # is done. This is Design Decision 7: narrow the mandatory-evidence branch
    # to implemented changes so legacy in-flight changes aren't flagged.
    tasks = change_dir / "tasks.md"
    if not tasks.exists():
        return ["missing required file: tasks.md"]
    if _tasks_all_complete(change_dir) and _changed_capabilities(change_dir):
        return [
            "reviews/grill-design.md missing — 实现已完成但独立 subagent design grilling 证据缺失。"
            "请用 /grill 跑独立设计追问并产出结构化决策记录。"
        ]

    # Fallback (compat with update-design-review-method, in-flight changes):
    # literal task marker.
    if not _has_design_review_task(tasks.read_text(encoding="utf-8")):
        return [
            "tasks.md missing pre-implementation batch-grill-me (grill-with-docs) or equivalent design review task"
        ]
    return []


def _normalize_question_index(raw: str) -> str | None:
    """Normalize an Open Questions / User Confirmation index to ``Q<n>``.

    Accepts ``1``, ``1.``, ``Q1``, ``q1``, and list/bold-wrapped forms like
    ``- **Q1**:`` (list marker and asterisks stripped). Returns None when no
    numeric index is present.
    """
    cleaned = raw.strip().strip(".")
    # Strip a leading list marker and any bold asterisks so the Q/number is
    # directly matchable.
    cleaned = re.sub(r"^[-*]\s*\**\s*", "", cleaned)
    m = re.match(r"(?:[Qq])?(\d+)", cleaned)
    if not m:
        return None
    return f"Q{m.group(1)}"


def _extract_open_question_indexes(text: str) -> list[str]:
    """Extract Open Questions entry indexes from ``## Open Questions``.

    Only entries with an explicit numeric/``Q<n>`` index count (``1.``, ``- **Q1**:``,
    ``- Q1 ...``). Placeholder entries (``- 无``, empty) are skipped.
    """
    section = _extract_h2_sections(text).get("Open Questions", "")
    if not section or _is_placeholder_body(section):
        return []
    indexes: list[str] = []
    for line in section.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        # Skip "no open questions" markers in any form (bare, numbered, "- 无").
        no_q = re.sub(r"^[-*]\s*", "", stripped)
        no_q = re.sub(r"^\d+[.、]\s*", "", no_q)
        no_q = re.sub(r"^\*\*", "", no_q)
        if no_q.strip() in {"无", "无。", "none", "none。", "没有", "无问题"}:
            continue
        # Read the leading index of a real entry (from the original line).
        m = re.match(r"^[-*]?\s*\**\s*(?:(?:Q|q)\d+|\d+)\s*[:：.]?\s*", stripped)
        if m:
            idx = _normalize_question_index(m.group(0))
            if idx:
                indexes.append(idx)
    return indexes


def _extract_user_confirmation_indexes(text: str) -> list[str]:
    """Extract confirmed Open Questions indexes from ``## User Confirmation``.

    A record counts only when the line is ``- **Q<n>**: 用户答复：<value>`` and
    the answer value is not an unconfirmed marker (``待确认``, ``pending``, etc.
    per UNCONFIRMED_TOKENS). This blocks the placeholder false-pass discovered
    in grill-confirmation-gate Q1.
    """
    section = _extract_h2_sections(text).get("User Confirmation", "")
    if not section:
        return []
    indexes: list[str] = []
    for line in section.splitlines():
        stripped = line.strip()
        # 容忍 `**Q8**（分支命名）:` 后缀（flow-policy-source P0 正则修复，
        # 与 workflow_guard._extract_user_confirmation_indexes 同步).
        m = re.match(r"^-\s+\*\*Q(\d+)\*\*(?:[^：:]*)\s*[:：]", stripped)
        if not m:
            continue
        answer_match = re.search(r"用户答复\s*[:：]\s*(.*?)(?:[；;]\s*确认时间|\s*$)", stripped)
        if not answer_match:
            continue
        answer = answer_match.group(1).strip().strip("`")
        if not answer or _is_unconfirmed_answer(answer):
            continue
        indexes.append(f"Q{m.group(1)}")
    return indexes


def _unconfirmed_open_questions(text: str) -> list[str]:
    """Open Questions without a matching confirmed User Confirmation record."""
    open_indexes = _extract_open_question_indexes(text)
    if not open_indexes:
        return []
    confirmed = set(_extract_user_confirmation_indexes(text))
    return [q for q in open_indexes if q not in confirmed]


def _extract_grill_decisions(text: str) -> list[str]:
    """Extract decision entries under ## Confirmed Decisions in grill-design.md.

    Only the canonical list-item format counts (``- **决策**: ...``, half- or
    full-width colon). The ``### Decision N:`` heading form is tolerated for
    display but does not satisfy the evidence threshold on its own — headings
    lack the required 理由/来源 fields, so counting them would let an agent pad
    the decision count without real content.
    """
    section = _extract_h2_sections(text).get("Confirmed Decisions", "")
    if not section or _is_placeholder_body(section):
        return []
    decisions: list[str] = []
    for line in section.splitlines():
        stripped = line.strip()
        if stripped.startswith("- **决策**：") or stripped.startswith("- **决策**:"):
            decisions.append(stripped)
    return decisions


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
        # Q11/代码层修正 11：verify_handoff_projection 扩为 verify_projection——
        # gen-1 校验 handoff.json == replay；gen-2 校验磁盘 workflow-state.json == replay。
        from agent.workflow.event_log import verify_projection

        errors.extend(verify_projection(change_dir))

    return errors


def _repo_root_for_change_dir(change_dir: Path) -> Path:
    if (
        change_dir.parent.name == "changes"
        and change_dir.parent.parent.name == "openspec"
    ):
        return change_dir.parent.parent.parent
    # Archived: openspec/changes/archive/<date>-<id>
    if (
        change_dir.parent.name == "archive"
        and change_dir.parent.parent.name == "changes"
        and change_dir.parent.parent.parent.name == "openspec"
    ):
        return change_dir.parent.parent.parent.parent
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


def _change_id_from_dir_name(dir_name: str) -> str:
    """Strip the leading ``YYYY-MM-DD-`` date prefix from an archive dir name."""
    match = re.match(r"\d{4}-\d{2}-\d{2}-(.+)", dir_name)
    return match.group(1) if match else dir_name


def _check_review_manifests(
    change_dir: Path, change_type: ChangeType, *, archived: bool = False
) -> list[str]:
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
    # in-flight change. Archived changes predate or satisfy this gate; the
    # --check-archived mode only verifies that EXISTING manifests still bind
    # their artifacts (drift detection), it does not demand a historical review.
    requires_building_review = (
        not archived
        and change_type.primary != "docs"
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
    change_id = _change_id_from_dir_name(change_dir.name)
    errors: list[str] = []
    for report_path in sorted(review_dir.glob("*-review.md")):
        phase = report_path.name.removesuffix("-review.md")
        errors.extend(verify_review_manifest(repo_root, change_id, phase, archived=archived))
    return errors


def _check_archived_projectable(change_dir: Path) -> list[str]:
    """归档 change 可投影校验（Q5/代码层修正 2）。

    只验证结构合法 + 所有 event_type 可识别（_apply / NON_STATE / milestones 集），
    不要求 seed 事件、不要求磁盘 workflow-state.json（老世代不落盘，Q13）。
    """
    if not (change_dir / "workflow-events.jsonl").exists():
        return []
    try:
        from agent.workflow.event_log import project_workflow_state

        project_workflow_state(change_dir)
    except Exception as exc:
        return [f"{change_dir.name}: archived change 事件日志不可投影: {exc}"]
    return []


def check_protected_path_explanations(
    repo_root: Path,
    *,
    changed_paths: set[str],
) -> list[str]:
    errors: list[str] = []
    try:
        rules = _load_protected_path_rules(repo_root)
    except RuntimeError as exc:
        # schema 非法（event_explained 缺 event_types 等）：不抛裸 traceback，
        # 以可读错误 fail-closed（building-review Issue 3）。
        return [f"scripts/flow-policy.json schema 非法: {exc}"]
    if rules is None:
        return [
            "scripts/flow-policy.json 缺失或损坏：受保护路径检查无法执行（fail-closed）。"
            "请修复策略文件后重跑。"
        ]
    for path in sorted(changed_paths):
        allowed_event_types = _allowed_event_types_for_protected_path(path, rules)
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


def _allowed_event_types_for_protected_path(
    path: str, rules: tuple[tuple[str, str, tuple[str, ...]], ...]
) -> tuple[str, ...] | None:
    for match_type, pattern, event_types in rules:
        if match_type == "exact" and path == pattern:
            return event_types
        if match_type == "prefix" and path.startswith(pattern):
            return event_types
        if match_type == "contains" and pattern in path:
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


def _changed_paths_since_base(
    repo_root: Path, base_ref: str, *, require_base: bool = False
) -> tuple[set[str], str | None]:
    """Return (changed_paths, warning) where warning is set when the base ref
    could not be resolved.

    ``git diff --name-only <base_ref>`` fails on a shallow checkout where the
    base ref is absent. With ``require_base`` the failure is reported as a
    warning the caller must treat as an error (fails closed, so CI can't
    silently skip protected-path checks); otherwise the check degrades to
    best-effort with a visible warning instead of silently passing.
    """
    result = subprocess.run(
        ["git", "diff", "--name-only", base_ref, "--"],
        cwd=repo_root,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        warning = (
            f"could not resolve base ref '{base_ref}' for protected-path check"
            f" (exit {result.returncode}): {result.stderr.strip()[:200]}"
        )
        if require_base:
            return set(), warning
        return set(), warning
    paths = {line.strip() for line in result.stdout.splitlines() if line.strip()}
    return paths, None


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
    parser.add_argument(
        "--require-base",
        action="store_true",
        help="Fail when the --base-ref cannot be resolved (CI gate: prevents "
        "protected-path checks from silently passing on a shallow checkout)",
    )
    parser.add_argument(
        "--check-archived",
        action="store_true",
        help="Also verify review manifests of archived changes, catching drift "
        "(e.g. post-PASS tasks edits) that active-only checks miss",
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

    if args.check_archived and not args.change:
        archive_root = changes_root / "archive"
        if archive_root.exists():
            for change_dir in sorted(p for p in archive_root.iterdir() if p.is_dir()):
                change_type = parse_change_type((change_dir / "proposal.md").read_text(encoding="utf-8"))[0] \
                    if (change_dir / "proposal.md").exists() else None
                if change_type is None:
                    continue
                errors.extend(_check_review_manifests(change_dir, change_type, archived=True))
                # Q5/代码层修正 2：归档 change 只验可投影（结构合法 + 类型可识别）
                errors.extend(_check_archived_projectable(change_dir))

    if not args.change and not args.skip_backlog:
        errors.extend(check_backlog_consistency(changes_root, Path(args.backlog)))

    if not args.skip_protected_paths:
        repo_root = _repo_root_for_changes_root(changes_root)
        changed_paths, base_warning = _changed_paths_since_base(
            repo_root, args.base_ref, require_base=args.require_base
        )
        if base_warning is not None:
            if args.require_base:
                errors.append(base_warning)
            else:
                print(f"WARNING: {base_warning}", file=sys.stderr)
        errors.extend(
            check_protected_path_explanations(repo_root, changed_paths=changed_paths)
        )
        # #127 P0：flow-policy.json 的 phases/review agent schema 结构校验
        errors.extend(_validate_policy_agent_schema(repo_root))

    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1

    print("OpenSpec artifact checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
