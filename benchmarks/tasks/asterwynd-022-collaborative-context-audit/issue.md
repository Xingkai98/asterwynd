# Audit the Context Compression Path and Write a Report

The agent context pipeline has two compression surfaces: `agent/context/summarizer.py`
(the pluggable `Summarizer` strategies) and `agent/memory/manager.py` (the
`MemoryManager` that decides *when* compaction runs). This task asks you to
produce a structured audit report that a teammate could act on without re-reading
every module.

This is intentionally a multi-part task — it is a good candidate for delegating
the parallel exploration to subagents and aggregating their findings (e.g. via an
orchestrator-worker or bidding pattern) rather than reading everything in one
context window.

## Task

Write a Markdown report to `docs/collab-context-audit.md` with exactly three
sections:

1. `## Summarizers` — list every `Summarizer` strategy in `agent/context/summarizer.py`
   (class name, `name`, whether it needs an LLM, and when the memory manager
   falls back to it).
2. `## Compaction Triggers` — from `agent/memory/manager.py`, describe every
   trigger that fires compaction (`max_tokens`, `compaction_gap`, and any
   explicit-compaction path), with the exact config field names.
3. `## Improvement Suggestion` — one concrete, small suggestion (a sentence or
   two) for tightening the compression budget, grounded in what you read.

The file must contain the literal words `summarizer` and `compact` in section 1
and section 2 respectively, so the check can be mechanical.

## Requirements

- The report must be real: it must reflect what `summarizer.py` and
  `manager.py` actually contain at the current commit.
- Do not modify any Python source — the deliverable is the report file only.
