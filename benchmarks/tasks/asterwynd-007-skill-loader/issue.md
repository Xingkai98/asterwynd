# Implement SkillLoader for Markdown Skills

The agent should support dynamically loaded "skills" — Markdown files with YAML frontmatter that define specialized behaviors and prompts. This allows the agent to be extended without modifying core code.

## Task

Implement `SkillLoader` in `agent/skills/loader.py` that:

1. Scans a configured directory for `.md` files
2. Parses YAML frontmatter from each file (delimited by `---`)
3. Extracts skill metadata: `name`, `description`, `tools` (list of required tool names), `always` (boolean)
4. Returns a list of `Skill` dataclass instances
5. The prompt body follows the frontmatter (everything after the second `---`)

## Requirements

- Create `agent/skills/loader.py`
- Use `dataclass` for the `Skill` type
- Handle missing or malformed frontmatter gracefully
- Empty skills directory should return an empty list (not error)
