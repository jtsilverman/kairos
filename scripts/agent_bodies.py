"""One reader of `.claude/agents/*.md` for every workflow generator.

The agent registry serves session-cached bodies and cannot spawn a new type,
so a generator embeds the body (frontmatter stripped) into its script. The
strip uses maxsplit on the fence line so a markdown `---` rule inside the body
never truncates it (the trap `gen_embedded.py` hit first).
"""

from __future__ import annotations

from pathlib import Path

_AGENTS = Path(__file__).resolve().parent.parent / ".claude" / "agents"


class BodyError(ValueError):
    """The file has no ---fenced frontmatter."""


def strip_frontmatter(md_path: Path) -> str:
    parts = md_path.read_text().split("---\n", 2)
    if len(parts) != 3:
        raise BodyError(f"frontmatter: {md_path.name} has no ---fenced frontmatter")
    return parts[2].strip()


def body(agent: str) -> str:
    """The body of `.claude/agents/<agent>.md`."""
    return strip_frontmatter(_AGENTS / f"{agent}.md")
