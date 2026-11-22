"""Input validation for lecture notes (pasted text or uploaded .txt files).

Validation runs BEFORE any API call, so invalid input never costs money and
always gets a clear, immediate message. Errors block generation; warnings are
shown to the student but generation can continue.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

MAX_CHARS = 40_000        # hard limit (~10k tokens) — keeps cost and latency bounded
SOFT_MAX_CHARS = 15_000   # above this we warn that generation will be slower
MIN_WORDS_WARNING = 25    # below this the notes are "very short"
MAX_UPLOAD_BYTES = 1_000_000
MAX_SUBJECT_CHARS = 120

_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_PHONE_RE = re.compile(r"(?<!\d)(?:\+?\d[\s-]?){10,13}(?!\d)")


@dataclass
class ValidationResult:
    ok: bool
    text: str = ""
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    stats: dict[str, int] = field(default_factory=dict)


def _stats(text: str) -> dict[str, int]:
    words = re.findall(r"\b\w+\b", text)
    return {
        "characters": len(text),
        "words": len(words),
        "lines": text.count("\n") + 1 if text else 0,
        "approx_tokens": round(len(text) / 4),
    }


def validate_notes(raw: str | None) -> ValidationResult:
    """Validate and normalise lecture notes text."""
    text = (raw or "").replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+\n", "\n", text)          # trailing spaces
    text = re.sub(r"\n{4,}", "\n\n\n", text).strip()  # huge blank gaps

    result = ValidationResult(ok=True, text=text, stats=_stats(text))

    if not text:
        result.ok = False
        result.errors.append("Please paste your lecture notes or upload a .txt file — the input is empty.")
        return result

    if len(text) > MAX_CHARS:
        result.ok = False
        result.errors.append(
            f"These notes are {len(text):,} characters long. The limit is {MAX_CHARS:,} "
            "characters (about 6,000 words). Please split them into smaller sections, "
            "for example one lecture or one topic at a time."
        )
        return result

    if len(text) > SOFT_MAX_CHARS:
        result.warnings.append(
            f"Long notes ({len(text):,} characters). Generation may take longer and the "
            "summary will compress more detail."
        )

    if result.stats["words"] < MIN_WORDS_WARNING:
        result.warnings.append(
            f"Very short notes ({result.stats['words']} words). The study pack will be "
            "limited to what these few lines contain."
        )

    letters = sum(c.isalpha() for c in text)
    if letters / max(len(text), 1) < 0.5:
        result.warnings.append(
            "This text contains few letters (mostly numbers or symbols). It may not be "
            "lecture notes."
        )

    if _EMAIL_RE.search(text) or _PHONE_RE.search(text):
        result.warnings.append(
            "The notes appear to contain an email address or phone number. Remove "
            "personal or confidential information before sending notes to an external AI service."
        )

    return result


def validate_subject(subject: str | None) -> tuple[str, list[str]]:
    """Return a cleaned subject string and any warnings."""
    s = re.sub(r"\s+", " ", (subject or "")).strip()
    warnings = []
    if len(s) > MAX_SUBJECT_CHARS:
        s = s[:MAX_SUBJECT_CHARS].rstrip()
        warnings.append(f"Subject was shortened to {MAX_SUBJECT_CHARS} characters.")
    return s, warnings


def decode_upload(data: bytes, filename: str = "") -> ValidationResult:
    """Decode an uploaded .txt file into a ValidationResult (not yet validated)."""
    if filename and not filename.lower().endswith(".txt"):
        return ValidationResult(ok=False, errors=["Only .txt files are supported."])
    if len(data) > MAX_UPLOAD_BYTES:
        return ValidationResult(ok=False, errors=["File is larger than 1 MB. Please upload a smaller .txt file."])
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):          # UTF-16 with BOM
        try:
            return ValidationResult(ok=True, text=data.decode("utf-16"))
        except UnicodeDecodeError:
            return ValidationResult(ok=False, errors=["Could not read the file as text."])
    if b"\x00" in data[:4096]:
        return ValidationResult(ok=False, errors=["This file looks binary, not plain text."])
    try:
        return ValidationResult(ok=True, text=data.decode("utf-8-sig"))
    except UnicodeDecodeError:
        return ValidationResult(ok=True, text=data.decode("latin-1"))  # never fails
