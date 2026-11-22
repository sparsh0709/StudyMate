"""Automatic evaluation metrics for a generated study pack.

These metrics are computed locally from the model output and the source notes.
They are PROXIES that support (not replace) human judgement:

* structure_ok            all expected sections present (summary, key concepts,
                          questions, revision points, checklist)
* question_count          number of questions detected
* answered_count          questions that have an answer
* grounded_questions      questions that are not "Not enough information" slots
* summary_words           words in the summary section
* summary_within_limit    summary_words <= limit for the chosen detail level (+10% tolerance)
* evidence_quotes / evidence_match_rate
                          V3 evidence quotes found verbatim in the notes
* novel_term_ratio        share of distinct content words in the output that never
                          appear in the notes — a rough signal of possibly
                          unsupported information (synonyms also count as "novel",
                          so it over-estimates; compare versions, not absolutes)
* duplicate_bullets       near-duplicate bullet pairs (Jaccard >= 0.8) in the revision
                          points — a repetition signal
* insufficient_flag       model returned INSUFFICIENT_NOTES

Human rubric scores (relevance, accuracy, completeness, clarity, consistency,
unsupported information) are recorded separately by the team in the CSV.
"""

from __future__ import annotations

import re
from itertools import combinations

from modules.output_formatter import StudyPack, count_unstructured_questions, verify_evidence
from modules.prompt_manager import DETAIL_LEVELS, DEFAULT_DETAIL

STOPWORDS = set("""
a about above after again against all also although always among an and any are
as at be because been before being below between both but by can cannot could did
do does doing down during each either else even every few for from further had has
have having he her here hers him his how however i if in into is it its itself
just least less like made make makes many may more most much must my neither no
nor not now of off often on once one only or other our out over own per rather
same she should since so some such than that the their them then there these they
this those though through thus to too two under until up upon us use used uses
using very via was we were what when where whether which while who whom whose why
will with within without would yet you your
answer answers concept concepts covered define defined definition definitions
evidence example examples explain explained explains factual conceptual important
key lecture main mention mentioned notes note point points question questions
revision summary summarise summarize checklist stated student students topic topics
understand understanding given describe described first second third three four
five another different each well able help helps include includes including
get set new way etc let see say put end lot yes its per off own too out any
""".split())


def _stem(w: str) -> str:
    for suf in ("ing", "ed", "es", "s"):
        if len(w) > len(suf) + 3 and w.endswith(suf):
            return w[: -len(suf)]
    return w


def content_terms(text: str) -> set[str]:
    words = re.findall(r"[a-z][a-z0-9]{2,}", (text or "").lower())
    return {_stem(w) for w in words if w not in STOPWORDS}


def novel_term_ratio(output: str, notes: str) -> float | None:
    out_terms = content_terms(output)
    if not out_terms:
        return None
    novel = out_terms - content_terms(notes)
    return round(len(novel) / len(out_terms), 3)


def novel_terms(output: str, notes: str, limit: int = 15) -> list[str]:
    return sorted(content_terms(output) - content_terms(notes))[:limit]


def _bullets(md: str) -> list[str]:
    return [re.sub(r"^\s*[-*\d.]+\s*(\[.\]\s*)?", "", ln).strip()
            for ln in md.splitlines() if re.match(r"^\s*([-*]|\d+[.)])\s+", ln)]


def duplicate_bullet_pairs(md: str, threshold: float = 0.8) -> int:
    sets = [content_terms(b) for b in _bullets(md)]
    sets = [s for s in sets if len(s) >= 3]
    dup = 0
    for a, b in combinations(sets, 2):
        if len(a & b) / len(a | b) >= threshold:
            dup += 1
    return dup


def word_count(text: str) -> int:
    return len(re.findall(r"\b\w+\b", text or ""))


def evaluate_pack(pack: StudyPack, notes: str, detail_level: str = DEFAULT_DETAIL) -> dict:
    limit = DETAIL_LEVELS.get(detail_level, DETAIL_LEVELS[DEFAULT_DETAIL])["summary_max_words"]
    full_output = "\n".join(pack.raw.values())

    if pack.questions:
        q_count = len(pack.questions)
        answered = sum(1 for q in pack.questions if q.answer and not q.placeholder)
        grounded = sum(1 for q in pack.questions if not q.placeholder)
    else:
        q_count = count_unstructured_questions(pack.questions_raw)
        answered = None   # cannot be determined reliably for unstructured output
        grounded = None

    evidence = verify_evidence(pack, notes)
    matched = sum(1 for e in evidence if e["Found in notes"])
    summary_words = word_count(pack.summary)

    structure_ok = bool(
        pack.summary and pack.key_concepts and len(pack.questions) == 5
        and pack.revision_points and pack.checklist
    )
    return {
        "structure_ok": structure_ok,
        "question_count": q_count,
        "answered_count": answered,
        "grounded_questions": grounded,
        "summary_words": summary_words,
        "summary_within_limit": summary_words <= limit * 1.1 if summary_words else None,
        "evidence_quotes": len(evidence),
        "evidence_match_rate": round(matched / len(evidence), 3) if evidence else None,
        "novel_term_ratio": novel_term_ratio(full_output, notes),
        "duplicate_bullets": duplicate_bullet_pairs(pack.revision_points),
        "insufficient_flag": pack.is_insufficient,
        "output_words": word_count(full_output),
    }
