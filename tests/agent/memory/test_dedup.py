# Tests for the write-time dedup judge (#75): three-branch classification,
# fallback behavior, and robust JSON parsing.
import pytest

from agent.llm import LLMResponse
from agent.memory.dedup import MemoryDedupJudge, _parse_judgment
from agent.memory.model import MemoryEntry, MemoryHit


class FakeLLM:
    def __init__(self, content: str) -> None:
        self._content = content
        self.last_model = None

    async def chat(self, messages, tools=None, model="gpt-4"):
        self.last_model = model
        return LLMResponse(content=self._content)


class RaisingLLM:
    async def chat(self, messages, tools=None, model="gpt-4"):
        raise RuntimeError("llm down")


def _hit(name: str, score: float = 0.8) -> MemoryHit:
    return MemoryHit(
        entry=MemoryEntry(
            name=name,
            description=f"{name} description",
            body=f"{name} body content",
        ),
        score=score,
    )


class TestMemoryDedupJudge:
    async def test_returns_new_without_llm(self):
        judge = MemoryDedupJudge(None)
        j = await judge.judge("incoming", [_hit("existing")])
        assert j.action == "new"
        assert j.target_name is None

    async def test_returns_new_without_candidates(self):
        judge = MemoryDedupJudge(FakeLLM('{"action":"update","target_name":"x"}'))
        j = await judge.judge("incoming", [])
        assert j.action == "new"

    async def test_parses_update(self):
        judge = MemoryDedupJudge(
            FakeLLM('{"action":"update","target_name":"role","reason":"supersedes"}')
        )
        j = await judge.judge("incoming", [_hit("role")])
        assert j.action == "update"
        assert j.target_name == "role"
        assert j.reason == "supersedes"

    async def test_parses_supplement(self):
        judge = MemoryDedupJudge(
            FakeLLM('{"action":"supplement","target_name":"prefs","reason":"adds detail"}')
        )
        j = await judge.judge("incoming", [_hit("prefs")])
        assert j.action == "supplement"
        assert j.target_name == "prefs"

    async def test_parses_conflict(self):
        judge = MemoryDedupJudge(
            FakeLLM('{"action":"conflict","target_name":"deadline","reason":"contradicts"}')
        )
        j = await judge.judge("incoming", [_hit("deadline")])
        assert j.action == "conflict"
        assert j.target_name == "deadline"

    async def test_parses_new(self):
        judge = MemoryDedupJudge(FakeLLM('{"action":"new","target_name":null,"reason":"unique"}'))
        j = await judge.judge("incoming", [_hit("existing")])
        assert j.action == "new"
        assert j.target_name is None

    async def test_handles_malformed_json(self):
        judge = MemoryDedupJudge(FakeLLM("not json at all"))
        j = await judge.judge("incoming", [_hit("existing")])
        assert j.action == "new"
        assert j.reason == "parse_failed"

    async def test_handles_llm_exception(self):
        judge = MemoryDedupJudge(RaisingLLM())
        j = await judge.judge("incoming", [_hit("existing")])
        assert j.action == "new"
        assert j.reason == "llm_call_failed"

    async def test_handles_invalid_action(self):
        judge = MemoryDedupJudge(FakeLLM('{"action":"delete","target_name":"x"}'))
        j = await judge.judge("incoming", [_hit("existing")])
        assert j.action == "new"
        assert j.reason == "invalid_action"

    async def test_tolerates_markdown_fenced_json(self):
        judge = MemoryDedupJudge(FakeLLM('```json\n{"action":"update","target_name":"role","reason":"r"}\n```'))
        j = await judge.judge("incoming", [_hit("role")])
        assert j.action == "update"
        assert j.target_name == "role"

    async def test_does_not_override_provider_model(self):
        """Regression: the judge must pass model=None so the LLM keeps its own
        model (hardcoding gpt-4 silently disabled dedup for Anthropic)."""
        llm = FakeLLM('{"action":"new","target_name":null,"reason":"x"}')
        judge = MemoryDedupJudge(llm=llm)
        await judge.judge("incoming", [_hit("existing")])
        assert llm.last_model is None

    async def test_below_recall_threshold_short_circuits_to_new(self):
        """Regression: candidates below recall_threshold never reach the LLM."""
        llm = FakeLLM('{"action":"update","target_name":"x","reason":"r"}')
        judge = MemoryDedupJudge(llm=llm, recall_threshold=0.9)
        j = await judge.judge("incoming", [_hit("existing", score=0.2)])
        assert j.action == "new"
        assert j.reason == "below_recall_threshold"

    async def test_candidate_at_threshold_reaches_llm(self):
        llm = FakeLLM('{"action":"update","target_name":"existing","reason":"r"}')
        judge = MemoryDedupJudge(llm=llm, recall_threshold=0.5)
        j = await judge.judge("incoming", [_hit("existing", score=0.6)])
        assert j.action == "update"
        assert j.target_name == "existing"


class TestParseJudgment:
    def test_extracts_json_object_from_prose(self):
        text = 'I decided: {"action":"conflict","target_name":"a","reason":"b"} — done.'
        j = _parse_judgment(text)
        assert j.action == "conflict"
        assert j.target_name == "a"

    def test_empty_text_is_new(self):
        j = _parse_judgment("")
        assert j.action == "new"

    def test_action_lowercased(self):
        j = _parse_judgment('{"action":"UPDATE","target_name":"x","reason":"r"}')
        assert j.action == "update"
