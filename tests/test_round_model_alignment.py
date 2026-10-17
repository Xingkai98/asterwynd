"""文档守卫：轮次口径必须与 witnessloop 的有界批次模型一致。

本 change 只改规则文档、规格与 checker 提示文案，没有运行时行为；因此这里用**显式
allowlist + per-file 映射**钉住规范面，而不是全仓扫描（历史归档与历史 review 记录的是
当时的规则，不能回填）。

新模型（witnessloop PR #40/#41，issue #24 已关）：
- 一轮 = 一个非空 medium+ 批次的闭环（开批 → 全修 → 只做修复验证 → 收口）；
- 批次冻结；验证期新问题只进 deferred；medium+ 全修，low/nit 可登记不修但须写理由；
- 最多 20 个已收口轮；第 20 轮后收口确认仍非空 ⇒ 超上限 BLOCKED + 建议推倒重开；
- 出口只有 PASS / BLOCKED + 成因 / 超上限 BLOCKED；CHANGES_REQUESTED 不是出口；
- 设计对抗环与实现审阅环共用同一模型；grill 的 frontier 追问轮豁免。
"""

from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]

# 显式 allowlist：只扫这些现行规范面。
ALLOWLIST = (
    "AGENTS.md",
    "README.md",
    "README_EN.md",
    "docs/requirements-process.md",
    "docs/interview-script/questions/Q14-dev-process.md",
    "openspec/specs/dev-workflow-state-machine/spec.md",
    "openspec/specs/change-documentation/spec.md",
    "scripts/check_openspec_artifacts.py",
)

# per-file 映射：每个文件必须含与它角色相符的核心要素，避免「七要素在合并文本里出现
# 一次就过」的假守卫。
PER_FILE_REQUIRED = {
    "AGENTS.md": (
        "非空 medium+ 批次",
        "批次冻结",
        "deferred",
        "20 个已收口轮",
        "建议推倒重开",
        "CHANGES_REQUESTED",
        "不是出口",
        "low/nit",
    ),
    "README.md": (
        "非空 medium+ 批次",
        "20 个已收口轮",
        "建议推倒重开",
    ),
    "README_EN.md": (
        "non-empty medium+ batch",
        "20 closed rounds",
        "revise the design",
    ),
    "docs/requirements-process.md": (
        "非空 medium+ 批次",
        "20 个已收口轮",
        "两环共用",
        "BLOCKED",
    ),
    "docs/interview-script/questions/Q14-dev-process.md": (
        "非空 medium+ 批次",
        "20 个已收口轮",
        "PASS",
        "BLOCKED",
    ),
    "openspec/specs/dev-workflow-state-machine/spec.md": (
        "非空 medium+ 批次",
        "批次冻结",
        "deferred",
        "20 个已收口轮",
        "收口确认",
        "建议推倒重开（revise the design）",
        "CHANGES_REQUESTED",
    ),
    "openspec/specs/change-documentation/spec.md": (
        "bounded-batch",
        "20 closed rounds",
        "deferred",
        "over-limit",
        "BLOCKED",
    ),
    "scripts/check_openspec_artifacts.py": (
        "非空 medium+ 批次",
        "20 个已收口轮",
        "建议推倒重开",
    ),
}

# 旧口径词表：不得出现在任何现行规范面。
FORBIDDEN_OLD_TERMS = (
    "无轮数上限",
    "最近两轮",
    "3 轮封顶",
    "轮数封顶",
    "round cap",
    "no fixed round limit",
    "no round limit",
    "再审直到收敛",
    "until convergence",
    "收敛即停",
)


def _read(relpath: str) -> str:
    return (ROOT / relpath).read_text(encoding="utf-8")


@pytest.mark.parametrize("relpath", ALLOWLIST)
def test_normative_surface_is_in_the_allowlist(relpath: str) -> None:
    """allowlist 里的文件必须真实存在（防止改名后守卫静默失效）。"""

    assert (ROOT / relpath).is_file(), relpath


@pytest.mark.parametrize("relpath,needles", sorted(PER_FILE_REQUIRED.items()))
def test_normative_surface_contains_batch_model(
    relpath: str, needles: tuple[str, ...]
) -> None:
    """每个规范面必须含有与它角色相符的新模型核心要素。"""

    content = _read(relpath)
    missing = [needle for needle in needles if needle not in content]
    assert not missing, f"{relpath} 缺少新模型要素: {missing}"


@pytest.mark.parametrize("relpath", ALLOWLIST)
def test_normative_surface_drops_old_round_model(relpath: str) -> None:
    """现行规范面不得再出现旧的「无上限 / 最近两轮 / 3 轮封顶」口径。"""

    content = _read(relpath)
    hits = [term for term in FORBIDDEN_OLD_TERMS if term in content]
    assert not hits, f"{relpath} 仍含旧口径词: {hits}"


def test_dev_workflow_spec_replaces_old_termination_requirement() -> None:
    """旧 Requirement 必须被新 Requirement 取代，不能两条并存。"""

    content = _read("openspec/specs/dev-workflow-state-machine/spec.md")
    assert (
        "### Requirement: 审阅闭环的轮次模型为有界批次，最多 20 个已收口轮"
        in content
    )
    assert "### Requirement: 审阅闭环的终止条件为收敛，而非轮数上限" not in content


def test_change_documentation_spec_references_bounded_batch_model() -> None:
    """设计阶段闭环的英文规格必须指向有界批次模型，而不是无固定轮数。"""

    content = _read("openspec/specs/change-documentation/spec.md")
    assert "bounded-batch" in content
    assert "no fixed round limit" not in content
    assert "until convergence" not in content


def test_checker_prompt_messages_use_batch_model() -> None:
    """checker 只改提示文案；旧提示必须消失，新提示必须出现。"""

    content = _read("scripts/check_openspec_artifacts.py")
    assert "审→改→再审直到收敛" not in content
    assert "非空 medium+ 批次" in content
    assert "20 个已收口轮" in content
    assert "建议推倒重开" in content


def test_local_entry_is_gitignored() -> None:
    """本地入口被 gitignore（防止把本地命令文件当成版本控制内的规范面）。"""

    gitignore = _read(".gitignore")
    assert ".claude" in gitignore
