#!/usr/bin/env python3
"""Slim project-rule checker (retired-gate replacement).

Implements only the six project rules that witnessloop does not cover:

1. Reference Implementation Research
2. Impact Analysis
3. benchmark smoke task requirement
4. tasks / archive-point completion (including archive-point grill evidence)
5. backlog consistency
6. building review `## 闭环出口` PASS verdict

Exit codes: 0 = pass, 1 = rule violations, 2 = missing changes root / usage error.
Change contracts, stage manifests, protected-write events, and active-stage grill
evidence are owned by witnessloop and are NOT re-checked here.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass
class ChangeType:
    primary: str
    secondary: tuple[str, ...]

    @property
    def all_types(self) -> set[str]:
        return {self.primary, *self.secondary}


ALLOWED_TYPES = {"feature", "bugfix", "research", "docs", "process", "refactor"}
DESIGN_TYPES = {"feature", "refactor", "process"}

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
STRUCTURAL_EXEMPTION_KEYWORDS = (
    "docs-only",
    "bugfix",
    "上游决策锁定",
    "无设计决策",
)
STRUCTURAL_EXEMPTION_RE_PATTERNS = (re.compile(r"方案已由.*决策"),)
EXEMPT_EVIDENCE_PATH_PATTERNS = ("docs/", "openspec/changes/archive/", "reviews/")
SELF_ADMITTED_INCOMPLETE_PHRASES = (
    "尚未完成",
    "待补充",
    "待调研",
    "tbd",
    "todo",
    "待确认",
)

PLACEHOLDER_ONLY = {
    "todo",
    "tbd",
    "n/a",
    "na",
    "待补充",
    "无",
    "待确认",
}

UNCONFIRMED_EXACT = {
    "todo", "tbd", "n/a", "na", "无", "none",
    "待确认", "未确认", "待定", "pending", "待补充", "占位", "未决",
}
UNCONFIRMED_STRONG = {
    "待主 agent", "待主agent", "待用户", "placeholder", "tobeconfirmed",
    "待拍板", "未拍板",
}
_UNCONFIRMED_MAX_ANSWER_LEN = 20
_UNCONFIRMED_STRIP = str.maketrans("", "", "。．.；;，,、 \t")

ARCHIVE_PATH_RE = re.compile(r"^openspec/changes/archive/(\d{4}-\d{2}-\d{2}-[^/]+)/")
ARCHIVE_ROOT_PREFIX = "openspec/changes/archive/"
ARCHIVE_DIR_SEGMENT_RE = re.compile(r"^openspec/changes/archive/([^/]+)/")
CHECKBOX_RE = re.compile(r"^[-*+]\s*\[([ xX])\]")
POST_MERGE_TAG_RE = re.compile(
    r"^\s*[-*+]\s*\[[ xX]\]\s*(?:\*\*)?(?:\d+(?:\.\d+)*)?(?:\*\*)?\s*"
    r"[（(]\s*post-merge\s*[)）]",
    re.IGNORECASE,
)


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
    change_dir: Path,
    proposal_text: str,
    change_type: ChangeType,
    *,
    assume_implemented: bool = False,
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
    #
    # 归档点门（issue #235 / D3 A′）：归档侧传 assume_implemented=True，使内容
    # 门槛不因归档 change 残留未勾任务而降级——否则一条 `- [ ]` 就能让本门静默
    # 返回空，正是本 change 要堵的绕开路径。
    if assume_implemented or _tasks_all_complete(change_dir):
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

def _tasks_all_complete(change_dir: Path) -> bool:
    """Return True when every checkbox line in tasks.md is checked.

    A tasks.md with no checkbox lines is treated as incomplete (no evidence of
    implementation), so the review gate does not fire prematurely.

    Scan is widened (issue #235 D4) to all three list markers and both checkbox
    cases: the old ``- [x]``/``* [x]`` pair silently ignored ``+ [ ]`` and
    ``[X]``, which would have let a ``+ [ ]`` line escape the completion gate.
    """
    tasks = change_dir / "tasks.md"
    if not tasks.exists():
        return False
    text = tasks.read_text(encoding="utf-8")
    checked = 0
    unchecked = 0
    for line in text.splitlines():
        match = CHECKBOX_RE.match(line.strip())
        if match is None:
            continue
        if match.group(1).lower() == "x":
            checked += 1
        else:
            unchecked += 1
    return checked > 0 and unchecked == 0

def _untagged_unchecked_tasks(change_dir: Path) -> list[str]:
    """Return unchecked task lines that lack a ``(post-merge)`` tag.

    Closing tasks that run *after* the PR merges ("关 issue" 类) are
    structurally impossible to tick at archive time, so they are exempted by an
    explicit ``(post-merge)`` marker. Everything else unchecked means the
    implementation is not finished (issue #235 D4) — silently tolerating it is
    exactly the bypass this change closes.
    """
    tasks = change_dir / "tasks.md"
    if not tasks.exists():
        return []
    untagged: list[str] = []
    for line in tasks.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        match = CHECKBOX_RE.match(stripped)
        if match is None or match.group(1).lower() == "x":
            continue
        if POST_MERGE_TAG_RE.match(line):
            continue
        untagged.append(stripped)
    return untagged

def _tasks_missing_evidence(change_dir: Path) -> str | None:
    """Return a reason string when tasks.md carries no proof of completion.

    ``tasks.md`` is the only evidence carrier for the completion dimension, so
    three shapes make ``_untagged_unchecked_tasks`` return nothing and the gate
    go silent — each is the same structural bypass as leaving one ``- [ ]``,
    i.e. closing the gate by *not writing* (or not ticking) a checkbox:

    1. no ``tasks.md`` at all;
    2. a prose / empty ``tasks.md`` with no checkbox line;
    3. checkbox lines that are **all unchecked** — e.g. every item tagged
       ``(post-merge)``, so the untagged scan finds nothing while nothing was
       actually done. 8 historical archives have this shape.

    So the floor is ">=1 checked box", matching ``_tasks_all_complete``'s
    ``checked > 0`` clause. The reason is returned (not a bare bool) so the
    error names the actual shape — an all-unchecked file reads very differently
    from a missing one, and a single message covering both misdescribes the
    former (building-review R3 finding 2).
    """
    tasks = change_dir / "tasks.md"
    if not tasks.exists():
        return "tasks.md 缺失"
    boxes = [
        match
        for match in (
            CHECKBOX_RE.match(line.strip())
            for line in tasks.read_text(encoding="utf-8").splitlines()
        )
        if match is not None
    ]
    if not boxes:
        return "tasks.md 无任何 checkbox 行"
    if not any(match.group(1).lower() == "x" for match in boxes):
        return "tasks.md 的 checkbox 行全部未勾选"
    return None


_REVIEW_EXIT_HEADING_PREFIX = "闭环出口"
# A leading token must be followed by a boundary, not a letter: rejects PASSED.
_REVIEW_EXIT_LEADING_TOKEN_RE = re.compile(
    r"(PASS|BLOCKED|CHANGES_REQUESTED)(?=$|[\s（(：:—\-/.*`~])",
    re.IGNORECASE,
)
_REVIEW_EXIT_ANY_TOKEN_RE = re.compile(
    r"(?<![A-Za-z])(PASS|BLOCKED|CHANGES_REQUESTED)(?![A-Za-z])",
    re.IGNORECASE,
)

def _strip_fenced_blocks(text: str) -> str:
    """Drop fenced code blocks (``` / ~~~) so quoted templates are ignored."""
    kept: list[str] = []
    fence: str | None = None
    for line in text.splitlines():
        stripped = line.lstrip()
        marker = stripped[:3]
        if fence is None:
            if marker in ("```", "~~~"):
                fence = marker
                continue
            kept.append(line)
        elif marker == fence:
            fence = None
    return "\n".join(kept)

def _review_exit_verdict(text: str) -> tuple[str, str | None]:
    """Parse the terminal verdict from the ``## 闭环出口`` section.

    Returns ``(status, verdict)`` with status one of ``missing`` /
    ``duplicate`` / ``empty`` / ``ambiguous`` / ``ok``. Only the first
    non-empty line counts; the four rules are documented in the change's
    design (retire-manifest-check Decision 2).
    """
    text = _strip_fenced_blocks(text)
    headings = list(re.finditer(r"^##\s+(.+?)\s*$", text, flags=re.MULTILINE))
    exits = [
        (index, match)
        for index, match in enumerate(headings)
        if match.group(1).strip().startswith(_REVIEW_EXIT_HEADING_PREFIX)
    ]
    if not exits:
        return "missing", None
    if len(exits) > 1:
        return "duplicate", None
    index, match = exits[0]
    end = headings[index + 1].start() if index + 1 < len(headings) else len(text)
    body = text[match.end():end]
    first = next((line.strip() for line in body.splitlines() if line.strip()), "")
    cleaned = first.lstrip("-*+ >`").strip()
    # Tolerate an ordered-list prefix (e.g. ``1. PASS``) the same way as the
    # other list markers.
    cleaned = re.sub(r"^\d+[.)]\s+", "", cleaned)
    lead = _REVIEW_EXIT_LEADING_TOKEN_RE.match(cleaned)
    if lead is None:
        return "empty", None
    verdict = lead.group(1).upper()
    rest = cleaned[lead.end():]
    if ("|" in rest or "｜" in rest) and _REVIEW_EXIT_ANY_TOKEN_RE.search(rest):
        return "ambiguous", None
    return "ok", verdict

def _review_exit_errors(report: Path, *, completion: bool) -> list[str]:
    """Errors for a building review's terminal exit.

    ``completion=False`` is the wide trigger: only a terminal non-PASS verdict
    is an error (docs / no-spec-delta / partial changes still get this check).
    ``completion=True`` additionally requires the section to exist and be PASS.
    """
    status, verdict = _review_exit_verdict(report.read_text(encoding="utf-8"))
    if status == "duplicate":
        return [
            "reviews/building-review.md 出现多个 `## 闭环出口` 小节，出口不唯一。"
        ]
    if status == "ok":
        if verdict == "PASS":
            return []
        return [
            f"reviews/building-review.md 的 `## 闭环出口` 为 {verdict}，"
            "审阅闭环未通过（要求 PASS）。"
        ]
    if not completion:
        return []
    if status == "missing":
        return [
            "reviews/building-review.md 缺少 `## 闭环出口` —— 终结 verdict 无法机械校验。"
            "请在报告末尾补 `## 闭环出口`，首个非空行写 PASS / BLOCKED / 超上限 BLOCKED。"
        ]
    if status == "ambiguous":
        return [
            "reviews/building-review.md 的 `## 闭环出口` 不唯一：首个非空行不得用 `|` "
            "列出多个终结出口。"
        ]
    return [
        "reviews/building-review.md 的 `## 闭环出口` 未填，或首个非空行不以终结 token "
        "（PASS / BLOCKED / CHANGES_REQUESTED）开头。"
    ]

def _check_building_review(
    change_dir: Path, change_type: ChangeType
) -> list[str]:
    """Review gate: wide terminal-non-PASS + completion-face PASS.

    The completion face fires once a non-docs change with a spec delta has all
    its tasks checked; it requires ``reviews/building-review.md`` with a PASS
    exit. The wide trigger runs whenever a building review exists: a terminal
    BLOCKED / CHANGES_REQUESTED verdict is always an error, preserving the
    retired manifest verdict check for docs / no-spec-delta / partial changes.
    A mid-round ``未定`` report is not flagged outside the completion face, so
    in-flight changes are not blocked.

    The retired asterwynd manifest (``reviews/<phase>-review-manifest.json``) is
    no longer required, produced or verified here (issue #316, first cut). Its
    producing module and CLI were deleted by ``retire-manifest-module`` (second cut).
    """
    review_report = change_dir / "reviews" / "building-review.md"
    requires_building_review = (
        change_type.primary != "docs"
        and _changed_capabilities(change_dir)
        and _tasks_all_complete(change_dir)
    )
    if requires_building_review:
        if not review_report.exists():
            return [
                "building-review.md missing — 独立 subagent 审阅未运行。"
                "请用 /review-loop 跑审阅闭环（一轮 = 非空 medium+ 批次：开批→全修→只验证→收口；最多 20 个已收口轮，超限则超上限 BLOCKED + 建议推倒重开）。"
            ]
        return _review_exit_errors(review_report, completion=True)
    if review_report.exists():
        return _review_exit_errors(review_report, completion=False)
    return []

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

def _resolve_base_ref(repo_root: Path, explicit: str | None) -> str:
    """Resolve the diff base used by the archive-point and protected-path checks.

    A non-empty explicit ``--base-ref`` always wins and keeps the caller's
    two-dot diff semantics. An empty/whitespace value is treated as omitted:
    passing ``--base-ref ""`` (e.g. an unset shell variable) must not silently
    skip both diff checks. When omitted, prefer the merge-base of
    ``HEAD`` and ``origin/master`` — the branch PRs are opened against — then
    that of ``HEAD`` and ``master``. The merge-base (three-dot semantics) keeps
    upstream commits out of the diff when the branch is behind, so a stale local
    ``master`` cannot make historical archives look newly archived and upstream
    protected-path edits are not reported as this branch's changes. If neither
    candidate resolves, return ``"master"`` so the existing ``--require-base``
    fail-closed / warning handling still applies.
    """
    if explicit is not None and explicit.strip():
        return explicit
    for candidate in ("origin/master", "master"):
        probe = subprocess.run(
            ["git", "rev-parse", "--verify", "--quiet", candidate],
            cwd=repo_root,
            capture_output=True,
            text=True, errors="replace",
        )
        if probe.returncode != 0:
            continue
        merge_base = subprocess.run(
            ["git", "merge-base", "HEAD", candidate],
            cwd=repo_root,
            capture_output=True,
            text=True, errors="replace",
        )
        resolved = merge_base.stdout.strip()
        base = resolved if merge_base.returncode == 0 and resolved else candidate
        print(
            f"INFO: using implicit base ref '{candidate}' -> {base}",
            file=sys.stderr,
        )
        return base
    return "master"

def _new_archive_dirs_since_base(
    repo_root: Path, base_ref: str
) -> tuple[list[str], list[str], str | None]:
    """Return (new_archive_dirs, non_conforming_paths, warning).

    ``new_archive_dirs`` are the ``<date>-<id>`` archive directory names that
    **this** diff newly creates — the change's archive point, i.e. the delivery
    moment the completeness gate must evaluate (issue #235 D1).

    Two filters, both load-bearing:

    * ``--diff-filter=AR``, not ``A``: when the source change directory exists
      in the base tree git reports the archive move as a rename (``R``), and
      ``A`` alone yields nothing for a byte-identical ``git mv``. Both forms
      produce the archive path, so both letters are required.
    * the directory must be **absent from the base tree**. Path matching alone
      cannot tell "newly archived in this PR" from "a file was added to an
      already-archived change" — and the latter is real (#234/#236/#238
      retrofitted manifests into archives). Without this filter, touching an
      old archive would drag that stale change through the full gate.

    ``non_conforming_paths`` are paths under the archive root that do **not**
    match the dated naming rule. Those are invisible to both this gate and
    ``iter_change_dirs`` (which skips ``archive``), so they must be reported
    rather than silently dropped.
    """
    result = subprocess.run(
        ["git", "diff", "--name-only", "--diff-filter=AR", base_ref, "--"],
        cwd=repo_root,
        capture_output=True,
        text=True, errors="replace",
    )
    if result.returncode != 0:
        warning = (
            f"could not resolve base ref '{base_ref}' for archived completion gate"
            f" (exit {result.returncode}): {result.stderr.strip()[:200]}"
        )
        return [], [], warning

    archive_names_in_base = _archive_dir_names_in_base(repo_root, base_ref)

    new_dirs: list[str] = []
    non_conforming: list[str] = []
    seen: set[str] = set()
    for raw in result.stdout.splitlines():
        path = raw.strip()
        if not path or not path.startswith(ARCHIVE_ROOT_PREFIX):
            continue
        if ARCHIVE_DIR_SEGMENT_RE.match(path) is None:
            # 归档根下的普通文件（如 `.gitkeep`）：不是归档目录，不评命名。
            continue
        match = ARCHIVE_PATH_RE.match(path)
        if match is None:
            non_conforming.append(path)
            continue
        dir_name = match.group(1)
        if dir_name in archive_names_in_base or dir_name in seen:
            continue
        seen.add(dir_name)
        new_dirs.append(dir_name)
    return sorted(new_dirs), sorted(non_conforming), None

def _archive_dir_names_in_base(repo_root: Path, base_ref: str) -> set[str]:
    """Archive directory names present in the base tree (empty on any failure).

    Failure to list the base tree degrades to "treat every matched dir as new",
    which is the stricter direction; the caller's ``--require-base`` handling
    covers the unresolvable-base case.
    """
    result = subprocess.run(
        ["git", "ls-tree", "-d", "--name-only", f"{base_ref}:openspec/changes/archive"],
        cwd=repo_root,
        capture_output=True,
        text=True, errors="replace",
    )
    if result.returncode != 0:
        return set()
    return {line.strip() for line in result.stdout.splitlines() if line.strip()}

def _check_new_archived_completion_gates(
    repo_root: Path,
    changes_root: Path,
    base_ref: str,
    *,
    require_base: bool,
) -> list[str]:
    """Run the archive-point completion gate over this diff's newly archived changes."""
    new_dirs, non_conforming, warning = _new_archive_dirs_since_base(repo_root, base_ref)
    errors: list[str] = []
    if warning is not None:
        if require_base:
            errors.append(warning)
        else:
            print(f"WARNING: {warning}", file=sys.stderr)
    for path in non_conforming:
        errors.append(
            f"{path}: 归档目录命名不合规（应为 openspec/changes/archive/"
            f"<YYYY-MM-DD>-<change-id>/），无法评估完成度门"
        )
    for dir_name in new_dirs:
        errors.extend(_check_archived_completion_gate(changes_root / "archive" / dir_name))
    return errors

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


def _check_archive_grill_evidence(change_dir: Path, change_type: ChangeType) -> list[str]:
    """Archive-point grill evidence for changes witnessloop's code_hits gate misses.

    witnessloop only requires the `grill` / `grill-adversarial` stages when the
    diff touches `require_change_for`. A process change that only edits
    `openspec/specs/**` and `docs/**` would otherwise lose the old archive gate's
    evidence checks, so the slim checker keeps them as part of archive completion.
    """

    if change_type.primary == "docs":
        return []
    if not (change_type.all_types & DESIGN_TYPES):
        return []
    if not _changed_capabilities(change_dir):
        return []

    errors: list[str] = []
    grill = change_dir / "reviews" / "grill-design.md"
    if not grill.exists():
        errors.append(
            "reviews/grill-design.md missing — 归档点要求独立 design grilling 证据。"
        )
    else:
        text = grill.read_text(encoding="utf-8")
        decisions = _extract_grill_decisions(text)
        if len(decisions) < 3:
            errors.append(
                f"reviews/grill-design.md 的 ## Confirmed Decisions 不足 3 条"
                f"（当前 {len(decisions)} 条）——独立 subagent design grilling 未完成"
            )
        missing = _unconfirmed_open_questions(text)
        if missing:
            errors.append(
                "reviews/grill-design.md 存在未确认的 Open Question: "
                + ", ".join(missing)
                + " ——每个 Open Question 必须有 ## User Confirmation 记录，未确认不允许归档"
            )

    adversarial = change_dir / "reviews" / "grill-adversarial.md"
    if not adversarial.exists():
        errors.append(
            "reviews/grill-adversarial.md missing — 归档点要求设计阶段审阅闭环证据"
        )
    return errors


def _check_archived_completion_gate(change_dir: Path) -> list[str]:
    """Evaluate completion on a newly archived change directory.

    Retains the old archive-point judgments that witnessloop does not own:
    RIR content threshold, building review existence/verdict, archive-point grill
    evidence, and tasks completion. Impact Analysis / benchmark smoke stay on the
    active-change face, matching the pre-retirement trigger matrix.
    """

    if not change_dir.exists():
        return []
    proposal = change_dir / "proposal.md"
    if not proposal.exists():
        return [f"{change_dir.name}: 新归档目录缺 proposal.md，无法评估完成度门"]
    proposal_text = proposal.read_text(encoding="utf-8")
    change_type = parse_change_type(proposal_text)[0]
    if change_type is None:
        return [f"{change_dir.name}: proposal.md 缺合法 Change Type，无法评估完成度门"]

    prefix = f"{change_dir.name}: "
    errors: list[str] = []

    if change_type.primary != "docs":
        errors.extend(
            prefix + error
            for error in _check_reference_implementation_research(
                change_dir, proposal_text, change_type, assume_implemented=True
            )
        )

    review_report = change_dir / "reviews" / "building-review.md"
    requires_building_review = (
        change_type.primary != "docs" and bool(_changed_capabilities(change_dir))
    )
    if requires_building_review and not review_report.exists():
        errors.append(
            prefix + "building-review.md missing — 归档点要求独立 subagent 审阅证据。"
            "请用 /review-loop 跑审阅闭环（一轮 = 非空 medium+ 批次：开批→全修→只验证→收口；最多 20 个已收口轮，超限则超上限 BLOCKED + 建议推倒重开）。"
        )
    elif review_report.exists():
        errors.extend(
            prefix + error
            for error in _review_exit_errors(
                review_report, completion=requires_building_review
            )
        )

    errors.extend(
        prefix + error
        for error in _check_archive_grill_evidence(change_dir, change_type)
    )

    missing_evidence = _tasks_missing_evidence(change_dir)
    if missing_evidence is not None:
        errors.append(
            prefix + f"{missing_evidence} —— 归档点无法评估完成度。"
            "tasks.md 至少要有 ≥1 条已勾选任务（closeout 类未完成项请标 `(post-merge)`）。"
        )
    else:
        for line in _untagged_unchecked_tasks(change_dir):
            errors.append(
                prefix
                + f"归档 change 存在未勾且未标 (post-merge) 的任务：{line}"
                + " ——closeout 类任务（合入后动作）请标 `(post-merge)`；其余请完成后再归档。"
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


def check_change(change_dir: Path) -> list[str]:
    """Check the four active-change rules (RIR/Impact/benchmark/building exit)."""

    errors: list[str] = []
    proposal = change_dir / "proposal.md"
    if not proposal.exists():
        return [f"{change_dir.name}: missing required file: proposal.md"]

    proposal_text = proposal.read_text(encoding="utf-8")
    change_type, type_errors = parse_change_type(proposal_text)
    errors.extend(f"{change_dir.name}: {error}" for error in type_errors)
    if change_type is None:
        return errors

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

    errors.extend(
        f"{change_dir.name}: {error}"
        for error in _check_building_review(change_dir, change_type)
    )
    errors.extend(
        f"{change_dir.name}: {error}"
        for error in _check_benchmark_smoke_task(change_dir, proposal_text)
    )
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--changes-root", default="openspec/changes")
    parser.add_argument("--change", help="Check a single active change")
    parser.add_argument("--backlog", default="docs/openspec-change-backlog.md")
    parser.add_argument(
        "--base-ref",
        default=None,
        help="Git ref to diff against (two-dot for explicit values). Omitted: "
        "merge-base of HEAD with origin/master, then master. Empty/whitespace is "
        "treated as omitted.",
    )
    parser.add_argument(
        "--skip-backlog",
        action="store_true",
        help="Skip backlog/archive consistency checks",
    )
    parser.add_argument(
        "--require-base",
        action="store_true",
        help="Fail when --base-ref cannot be resolved",
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
        errors.extend(check_change(change_dir))

    if not args.change and not args.skip_backlog:
        errors.extend(check_backlog_consistency(changes_root, Path(args.backlog)))

    if not args.change:
        repo_root = _repo_root_for_changes_root(changes_root)
        base_ref = _resolve_base_ref(repo_root, args.base_ref)
        errors.extend(
            _check_new_archived_completion_gates(
                repo_root,
                changes_root,
                base_ref,
                require_base=args.require_base,
            )
        )

    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1

    print("Project rule checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
