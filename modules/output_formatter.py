"""Output formatter — turns raw model text into a structured study pack.

V2 and V3 ask for fixed Markdown headings, so their output can be split into
sections reliably. V1 (baseline) has no format, so parsing falls back to
showing the raw text and records that the structure was missing. That
difference is itself one of the things the experiments measure.

This module also implements the evidence check used by the Verification tab:
V3 asks the model to quote the notes word-for-word, and we check each quote
against the original notes locally. A matching quote shows that the claim is
anchored to the notes; it does NOT prove the claim is correct.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime

INSUFFICIENT_PREFIX = "INSUFFICIENT_NOTES:"
NOT_ENOUGH_Q = "not enough information in the notes"


@dataclass
class Question:
    number: int
    qtype: str          # "Factual", "Conceptual" or ""
    text: str
    answer: str
    evidence: str = ""
    placeholder: bool = False   # V3 "Not enough information..." slot


@dataclass
class StudyPack:
    main_topic: str = ""
    summary: str = ""
    key_concepts: str = ""
    questions: list[Question] = field(default_factory=list)
    questions_raw: str = ""
    revision_points: str = ""
    definitions: str = ""
    checklist: str = ""
    coverage: str = ""
    raw: dict[str, str] = field(default_factory=dict)
    structured: dict[str, bool] = field(default_factory=dict)  # task -> headings found
    insufficient: dict[str, str] = field(default_factory=dict)  # task -> reason

    @property
    def is_insufficient(self) -> bool:
        return bool(self.insufficient)


# ---------------------------------------------------------------- parsing ---

def split_sections(md: str) -> dict[str, str]:
    """Split Markdown on level-2 headings: {'summary': '...', 'key concepts': '...'}."""
    sections: dict[str, str] = {}
    parts = re.split(r"^##\s+(?!#)(.+?)\s*$", md, flags=re.MULTILINE)
    # parts = [preamble, heading1, body1, heading2, body2, ...]
    for i in range(1, len(parts) - 1, 2):
        key = re.sub(r"[*_`:]", "", parts[i]).strip().lower()
        sections[key] = parts[i + 1].strip()
    return sections


def _find(sections: dict[str, str], *names: str) -> str | None:
    for n in names:
        for key, body in sections.items():
            if key.startswith(n):
                return body
    return None


def detect_insufficient(text: str) -> str | None:
    m = re.search(rf"{INSUFFICIENT_PREFIX}\s*(.*)", text or "")
    return m.group(1).strip() if m else None


_Q_HEAD = re.compile(r"^#{2,4}\s*Q(\d+)[.:)]?\s*(?:\((\w+)\))?\s*(.*)$", re.MULTILINE)


def parse_questions(md: str) -> list[Question]:
    """Parse '### Qn. (Type) text' blocks with **Answer:** / **Evidence:** lines."""
    heads = list(_Q_HEAD.finditer(md))
    out: list[Question] = []
    for i, h in enumerate(heads):
        end = heads[i + 1].start() if i + 1 < len(heads) else len(md)
        body = md[h.end():end]
        ans = re.search(r"\*\*Answer:?\*\*:?\s*(.+?)(?=\n\s*\*\*Evidence|\Z)", body, re.S)
        ev = re.search(r"\*\*Evidence:?\*\*:?\s*(.+)", body)
        text = h.group(3).strip()
        out.append(Question(
            number=int(h.group(1)),
            qtype=(h.group(2) or "").capitalize(),
            text=text,
            answer=ans.group(1).strip() if ans else "",
            evidence=ev.group(1).strip().strip('"“”') if ev else "",
            placeholder=NOT_ENOUGH_Q in text.lower(),
        ))
    return out


def count_unstructured_questions(text: str) -> int:
    """Heuristic question count for unstructured (V1) output."""
    pattern = r"^\s*(?:\*\*)?(?:#+\s*)?(?:Q(?:uestion)?\s*)?\d+[.):]\s*(?:\*\*)?.*\?"
    return len(re.findall(pattern, text, re.MULTILINE | re.IGNORECASE))


def build_study_pack(task_texts: dict[str, str]) -> StudyPack:
    """Build a StudyPack from {'SUMMARY': text, 'QUESTIONS': text, 'REVISION': text}."""
    pack = StudyPack(raw=dict(task_texts))

    for task, text in task_texts.items():
        reason = detect_insufficient(text)
        if reason is not None:
            pack.insufficient[task] = reason

    s = split_sections(task_texts.get("SUMMARY", ""))
    pack.main_topic = _find(s, "main topic") or ""
    pack.summary = _find(s, "summary") or ""
    pack.key_concepts = _find(s, "key concept") or ""
    pack.structured["SUMMARY"] = bool(pack.summary and pack.key_concepts)
    if not pack.summary and "SUMMARY" not in pack.insufficient:
        pack.summary = task_texts.get("SUMMARY", "")  # unstructured fallback

    q_text = task_texts.get("QUESTIONS", "")
    pack.questions = parse_questions(q_text)
    pack.questions_raw = q_text
    pack.structured["QUESTIONS"] = len(pack.questions) > 0

    r = split_sections(task_texts.get("REVISION", ""))
    pack.revision_points = _find(r, "revision point") or ""
    pack.definitions = _find(r, "key definition", "definition") or ""
    pack.checklist = _find(r, "quick revision checklist", "revision checklist", "checklist") or ""
    pack.coverage = _find(r, "source coverage", "coverage") or ""
    pack.structured["REVISION"] = bool(pack.revision_points and pack.checklist)
    if not pack.revision_points and "REVISION" not in pack.insufficient:
        pack.revision_points = task_texts.get("REVISION", "")
    return pack


# ------------------------------------------------------------ verification ---

def _norm(s: str) -> str:
    s = s.lower().replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    s = re.sub(r"[^\w\s]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def extract_evidence_quotes(pack: StudyPack) -> list[tuple[str, str]]:
    """Return [(where, quote)] for every evidence quote in the pack."""
    quotes: list[tuple[str, str]] = []
    for line in pack.key_concepts.splitlines():
        m = re.search(r"\*\*(.+?)\*\*.*?Evidence:?\**\s*[\"“](.+?)[\"”]", line)
        if m:
            quotes.append((f"Concept: {m.group(1).strip(':')}", m.group(2)))
    for q in pack.questions:
        if q.evidence and not q.placeholder:
            quotes.append((f"Q{q.number}", q.evidence))
    return quotes


def check_quote(quote: str, notes: str) -> bool:
    """True if the quote appears in the notes (case/punctuation-insensitive)."""
    nq = _norm(quote)
    return bool(nq) and nq in _norm(notes)


def verify_evidence(pack: StudyPack, notes: str) -> list[dict[str, object]]:
    return [
        {"Location": where, "Quote": quote, "Found in notes": check_quote(quote, notes)}
        for where, quote in extract_evidence_quotes(pack)
    ]


# ----------------------------------------------------------------- export ---

def to_markdown(pack: StudyPack, subject: str, version: str, model: str) -> str:
    """Full study pack as a downloadable Markdown document."""
    title = subject.strip() or "Lecture Notes"
    lines = [
        f"# StudyMate Study Pack — {title}",
        "",
        f"_Generated {datetime.now():%d %b %Y, %H:%M} with prompt {version.upper()} "
        f"and model `{model}`._",
        "",
        "> AI-generated content can contain errors. Check every answer against your "
        "original lecture notes before relying on it.",
        "",
    ]
    if pack.is_insufficient:
        lines += ["## Notice", ""]
        lines += [f"- {t.title()}: {r}" for t, r in pack.insufficient.items()]
        lines.append("")
    if pack.main_topic:
        lines += ["## Main Topic", "", pack.main_topic, ""]
    lines += ["## Summary", "", pack.summary or "_Not generated._", ""]
    if pack.key_concepts:
        lines += ["## Key Concepts", "", pack.key_concepts, ""]
    lines += ["## Practice Questions", ""]
    if pack.questions:
        for q in pack.questions:
            tag = f" ({q.qtype})" if q.qtype else ""
            lines += [f"### Q{q.number}.{tag} {q.text}", ""]
            if q.answer:
                lines += [f"**Answer:** {q.answer}", ""]
            if q.evidence:
                lines += [f'**Evidence:** "{q.evidence}"', ""]
    else:
        lines += [pack.questions_raw or "_Not generated._", ""]
    lines += ["## Revision Points", "", pack.revision_points or "_Not generated._", ""]
    if pack.definitions:
        lines += ["## Key Definitions", "", pack.definitions, ""]
    if pack.checklist:
        lines += ["## Quick Revision Checklist", "", pack.checklist, ""]
    if pack.coverage:
        lines += ["## Source Coverage", "", pack.coverage, ""]
    return "\n".join(lines).strip() + "\n"
