# Implement MemoryManager with AutoCompact

Long agent conversations accumulate messages and eventually exceed the LLM's context window. The project needs a memory manager that tracks token usage and compresses message history when needed.

## Task

Implement `MemoryManager` in `agent/memory/manager.py` that:

1. Maintains a list of `Message` objects
2. Tracks total token count using `tiktoken`
3. Triggers compaction when token count exceeds `max_tokens` (default 80,000)
4. Compaction preserves system messages and the most recent N messages (default 10)
5. Older messages are replaced with an LLM-generated summary
6. Provides a `compact_if_needed()` method that checks and compresses in one call

## Requirements

- Create `agent/memory/manager.py`
- Use the `tiktoken` library for token counting
- Compaction must preserve conversation context while reducing token usage
- Handle edge cases: empty message list, messages shorter than the keep threshold
