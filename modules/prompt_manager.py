"""Prompt manager — loads versioned prompt files and renders chat messages.

Each prompt file in ``prompts/`` (prompt_v1.txt, prompt_v2.txt, ...) contains
four sections separated by ``=== NAME ===`` markers:

    SYSTEM     shared system message for all three tasks
    SUMMARY    Task A — summary + key concepts
    QUESTIONS  Task B — five practice questions with answers
    REVISION   Task C — revision points, definitions, checklist

Lines starting with ``#`` before the first marker are a header comment that
describes the version (shown in the UI).

Keeping prompts in plain text files (not inside Python code) means the prompt
engineering work is visible, diff-able in Git and editable without touching
code — an important design decision for this project.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"

TASKS = ("SUMMARY", "QUESTIONS", "REVISION")
TASK_LABELS = {
    "SUMMARY": "A. Summary Generator",
    "QUESTIONS": "B. Practice Question Generator",
    "REVISION": "C. Revision Generator",
}

# Detail level -> numeric limits substituted into V2/V3 prompts.
DETAIL_LEVELS = {
    "Brief": {
        "SUMMARY_WORDS": "80-120",
        "CONCEPT_COUNT": "3-5",
        "POINT_COUNT": "5",
        "CHECKLIST_COUNT": "5",
        "summary_max_words": 120,
    },
    "Standard": {
        "SUMMARY_WORDS": "150-200",
        "CONCEPT_COUNT": "5-7",
        "POINT_COUNT": "6-8",
        "CHECKLIST_COUNT": "6-8",
        "summary_max_words": 200,
    },
    "Detailed": {
        "SUMMARY_WORDS": "250-300",
        "CONCEPT_COUNT": "7-10",
        "POINT_COUNT": "8-12",
        "CHECKLIST_COUNT": "8-10",
        "summary_max_words": 300,
    },
}
DEFAULT_DETAIL = "Standard"

_SECTION_RE = re.compile(r"^===\s*([A-Z]+)\s*===\s*$", re.MULTILINE)


@dataclass
class PromptVersion:
    """One parsed prompt file."""

    version: str               # e.g. "v3"
    path: Path
    title: str                 # first header line, e.g. "Version 3: Grounded ..."
    description: str           # remaining header comment lines
    sections: dict[str, str] = field(default_factory=dict)

    @property
    def label(self) -> str:
        return f"{self.version.upper()} — {self.title}"


class PromptError(ValueError):
    """Raised when a prompt file is missing or malformed."""


def list_versions(prompts_dir: Path = PROMPTS_DIR) -> list[str]:
    """Return available versions sorted numerically, e.g. ['v1', 'v2', 'v3']."""
    found = []
    for p in prompts_dir.glob("prompt_v*.txt"):
        m = re.fullmatch(r"prompt_(v\d+)\.txt", p.name)
        if m:
            found.append(m.group(1))
    return sorted(found, key=lambda v: int(v[1:]))


def load_version(version: str, prompts_dir: Path = PROMPTS_DIR) -> PromptVersion:
    """Parse ``prompts/prompt_<version>.txt`` into its sections."""
    path = prompts_dir / f"prompt_{version}.txt"
    if not path.exists():
        raise PromptError(f"Prompt file not found: {path.name}")
    text = path.read_text(encoding="utf-8")

    markers = list(_SECTION_RE.finditer(text))
    if not markers:
        raise PromptError(f"{path.name} has no '=== SECTION ===' markers")

    header_lines = [
        ln.lstrip("#").strip()
        for ln in text[: markers[0].start()].splitlines()
        if ln.strip().startswith("#")
    ]
    title = header_lines[0] if header_lines else version
    title = re.sub(r"^StudyMate Prompt\s*[—-]\s*", "", title)
    title = re.sub(r"^Version\s*\d+\s*:\s*", "", title)
    description = " ".join(header_lines[1:]).split("Placeholders:")[0].strip()

    sections: dict[str, str] = {}
    for i, m in enumerate(markers):
        end = markers[i + 1].start() if i + 1 < len(markers) else len(text)
        sections[m.group(1)] = text[m.end():end].strip()

    missing = [s for s in ("SYSTEM", *TASKS) if s not in sections]
    if missing:
        raise PromptError(f"{path.name} is missing sections: {', '.join(missing)}")

    return PromptVersion(version, path, title, description, sections)


def _fill(template: str, values: dict[str, str]) -> str:
    """Replace {{PLACEHOLDER}} tokens. Unknown placeholders are left visible."""
    def repl(m: re.Match) -> str:
        return values.get(m.group(1), m.group(0))
    return re.sub(r"\{\{([A-Z_]+)\}\}", repl, template)


def render_messages(
    version: str,
    task: str,
    notes: str,
    subject: str = "",
    detail_level: str = DEFAULT_DETAIL,
    prompts_dir: Path = PROMPTS_DIR,
) -> list[dict[str, str]]:
    """Build the chat ``messages`` list for one task of one prompt version."""
    if task not in TASKS:
        raise PromptError(f"Unknown task '{task}'. Expected one of {TASKS}")
    pv = load_version(version, prompts_dir)
    limits = DETAIL_LEVELS.get(detail_level, DETAIL_LEVELS[DEFAULT_DETAIL])
    values = {
        "NOTES": notes.strip(),
        "SUBJECT": subject.strip() or "the lecture",
        "DETAIL_LEVEL": detail_level,
        **{k: str(v) for k, v in limits.items() if k.isupper()},
    }
    return [
        {"role": "system", "content": _fill(pv.sections["SYSTEM"], values)},
        {"role": "user", "content": _fill(pv.sections[task], values)},
    ]
