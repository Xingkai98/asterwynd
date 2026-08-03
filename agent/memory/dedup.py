"""Write-time dedup and conflict detection for long-term memory (#75).

``MemoryDedupJudge`` classifies an incoming memory against top-k similar
existing memories into one of: ``new`` / ``supplement`` / ``update`` /
``conflict``. The three-branch judgment is the interview-carrying feature of
this change (Decision 2); a None LLM degrades to ``new`` so a missing model
never blocks writes.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from agent.memory.model import MemoryHit

if TYPE_CHECKING:
    from agent.llm import LLM

logger = logging.getLogger("asterwynd.memory.dedup")

_ACTIONS = frozenset({"new", "supplement", "update", "conflict"})


@dataclass
class Judgment:
    """Result of the LLM dedup pass.

    ``action``: new / supplement / update / conflict.
    ``target_name``: existing entry the action applies to (None for new).
    ``reason``: human-readable explanation recorded in the change log.
    """

    action: str = "new"
    target_name: str | None = None
    reason: str = ""


_SYSTEM_PROMPT = (
    "You are the write-time dedup judge for a coding agent's long-term memory store. "
    "An incoming memory is being saved. You are given up to 5 semantically similar "
    "existing memories. Decide the relationship and return ONLY a JSON object with "
    "keys: action (one of \"new\", \"supplement\", \"update\", \"conflict\"), "
    "target_name (the name of the existing memory the action applies to, or null), "
    "reason (one short sentence explaining the decision). "
    "Rules: \"supplement\" = the incoming adds detail to an existing memory without "
    "contradicting it; \"update\" = the incoming supersedes/replaces an existing "
    "memory's content; \"conflict\" = the incoming contradicts an existing memory "
    "and both should be kept, marked against each other; \"new\" = the incoming is "
    "not covered by any existing memory. Do not invent a target_name that is not in "
    "the candidates."
)

_USER_TEMPLATE = """\
Incoming memory:
{incoming}

Similar existing memories:
{candidates}
"""


class MemoryDedupJudge:
    """Classify an incoming memory against similar existing memories via LLM.

    ``recall_threshold`` is the minimum similarity for a candidate to reach the
    LLM; below it the write short-circuits to ``new`` (zero LLM cost). Passing
    ``model=None`` makes the LLM use its own configured model, so the judge
    never overrides the provider's model (e.g. Anthropic).
    """

    def __init__(
        self,
        llm: "LLM | None" = None,
        model: str | None = None,
        recall_threshold: float = 0.5,
    ) -> None:
        self._llm = llm
        self._model = model
        self._recall_threshold = recall_threshold

    async def judge(
        self,
        incoming_text: str,
        candidates: list[MemoryHit],
    ) -> Judgment:
        """Return a Judgment for the incoming text given candidate memories."""
        if self._llm is None or not candidates:
            return Judgment("new", None, "no_llm_or_no_candidates")

        strong = [c for c in candidates if c.score >= self._recall_threshold]
        if not strong:
            return Judgment("new", None, "below_recall_threshold")

        candidates_text = _format_candidates(strong)
        from agent.message import Message

        try:
            response = await self._llm.chat(
                messages=[
                    Message(role="system", content=_SYSTEM_PROMPT),
                    Message(
                        role="user",
                        content=_USER_TEMPLATE.format(
                            incoming=incoming_text,
                            candidates=candidates_text,
                        ),
                    ),
                ],
                tools=None,
                model=self._model,
            )
        except Exception:
            logger.warning("MemoryDedupJudge: LLM call failed, falling back to new", exc_info=True)
            return Judgment("new", None, "llm_call_failed")

        return _parse_judgment(response.content or "")


def _format_candidates(candidates: list[MemoryHit]) -> str:
    lines: list[str] = []
    for index, hit in enumerate(candidates, start=1):
        entry = hit.entry
        body_preview = entry.body.replace("\n", " ").strip()[:200]
        lines.append(
            f"{index}. name={entry.name} type={entry.type} "
            f"similarity={hit.score:.2f}\n"
            f"   description: {entry.description}\n"
            f"   body: {body_preview}"
        )
    return "\n".join(lines)


def _parse_judgment(text: str) -> Judgment:
    """Parse the LLM's JSON answer, tolerating markdown fences and trailing text."""
    cleaned = text.strip()
    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if match is None:
        return Judgment("new", None, "parse_failed")
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return Judgment("new", None, "parse_failed")
    if not isinstance(data, dict):
        return Judgment("new", None, "parse_failed")
    action = str(data.get("action") or "new").strip().lower()
    if action not in _ACTIONS:
        return Judgment("new", None, "invalid_action")
    target = data.get("target_name")
    if target is not None:
        target = str(target)
    reason = str(data.get("reason") or action)
    return Judgment(action=action, target_name=target, reason=reason)
