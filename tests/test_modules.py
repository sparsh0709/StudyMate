"""Unit tests for StudyMate modules that do not need the OpenAI API.

Run:  python -m pytest -q

The model-output strings below are HAND-WRITTEN PARSER FIXTURES used only to
test parsing and metric code. They are not AI outputs and are never reported
as test results.
"""

from __future__ import annotations

import re
from types import SimpleNamespace

import pytest

from modules import ai_generator as ag
from modules.evaluator import duplicate_bullet_pairs, evaluate_pack, novel_term_ratio
from modules.input_validator import MAX_CHARS, decode_upload, validate_notes, validate_subject
from modules.output_formatter import (
    build_study_pack, check_quote, parse_questions, to_markdown, verify_evidence,
)
from modules.prompt_manager import TASKS, list_versions, load_version, render_messages

NOTES = ("Binary search works on a sorted array. Each comparison halves the search space, "
         "so the worst-case time complexity is O(log n). Linear search takes O(n) time.")

FIXTURE_SUMMARY = """## Main Topic
Binary search on sorted arrays.

## Summary
Binary search needs a sorted array and halves the search space each step.

## Key Concepts
- **Sorted input**: required before searching. Evidence: "Binary search works on a sorted array"
- **Complexity**: O(log n) in the worst case. Evidence: "worst-case time complexity is O(log n)"
- **Made up**: not real. Evidence: "this quote is not in the notes"
"""

FIXTURE_QUESTIONS = "## Practice Questions\n\n" + "\n\n".join(
    f"### Q{i}. ({'Factual' if i % 2 else 'Conceptual'}) Question {i}?\n"
    f"**Answer:** Answer {i}.\n**Evidence:** \"Each comparison halves the search space\""
    for i in range(1, 5)
) + "\n\n### Q5. Not enough information in the notes for another question."

FIXTURE_REVISION = """## Revision Points
- Binary search requires a sorted array.
- Worst case is O(log n).

## Key Definitions
- **Binary search**: halves the search space each comparison.

## Quick Revision Checklist
- [ ] I can state the complexity of binary search.

## Source Coverage
- **Covered in the notes:** binary search, linear search
- **Missing or unclear in the notes:** the algorithm steps
"""


# ------------------------------------------------------------ validator ---
class TestValidator:
    def test_empty_rejected(self):
        for raw in ("", "   \n\t ", None):
            r = validate_notes(raw)
            assert not r.ok and "empty" in r.errors[0]

    def test_over_length_rejected(self):
        r = validate_notes("a" * (MAX_CHARS + 1))
        assert not r.ok and "limit" in r.errors[0]

    def test_short_notes_warn_but_pass(self):
        r = validate_notes("Stack: LIFO. push adds, pop removes.")
        assert r.ok and any("Very short" in w for w in r.warnings)

    def test_normal_notes_clean(self):
        r = validate_notes(NOTES * 3)
        assert r.ok and not r.errors

    def test_pii_warning(self):
        r = validate_notes(NOTES + " Contact prof at someone@bennett.edu.in or 9876543210.")
        assert r.ok and any("personal" in w for w in r.warnings)

    def test_whitespace_normalised(self):
        r = validate_notes("line one   \r\n\n\n\n\n\nline two")
        assert r.text == "line one\n\n\nline two"

    def test_subject_trimmed(self):
        s, w = validate_subject("  Data   Structures " + "x" * 200)
        assert s.startswith("Data Structures") and len(s) <= 120 and w

    def test_upload_decoding(self):
        assert decode_upload("héllo".encode("utf-8"), "a.txt").text == "héllo"
        assert not decode_upload(b"abc", "a.pdf").ok
        assert not decode_upload(b"\x00\x01binary", "a.txt").ok
        assert decode_upload("hi".encode("utf-16"), "a.txt").text == "hi"


# ------------------------------------------------------- prompt manager ---
class TestPromptManager:
    def test_three_versions_exist(self):
        assert list_versions()[:3] == ["v1", "v2", "v3"]

    @pytest.mark.parametrize("version", ["v1", "v2", "v3"])
    def test_each_version_has_all_tasks(self, version):
        pv = load_version(version)
        for task in ("SYSTEM", *TASKS):
            assert pv.sections[task].strip()

    @pytest.mark.parametrize("version", ["v1", "v2", "v3"])
    @pytest.mark.parametrize("task", TASKS)
    def test_render_fills_all_placeholders(self, version, task):
        msgs = render_messages(version, task, NOTES, "Binary Search", "Brief")
        assert [m["role"] for m in msgs] == ["system", "user"]
        joined = msgs[0]["content"] + msgs[1]["content"]
        assert not re.search(r"\{\{[A-Z_]+\}\}", joined)
        assert NOTES in msgs[1]["content"]

    def test_detail_level_changes_v2_limits(self):
        brief = render_messages("v2", "SUMMARY", NOTES, "x", "Brief")[1]["content"]
        detailed = render_messages("v2", "SUMMARY", NOTES, "x", "Detailed")[1]["content"]
        assert "80-120" in brief and "250-300" in detailed

    def test_v3_delimits_notes_and_has_grounding(self):
        msgs = render_messages("v3", "QUESTIONS", NOTES, "x")
        assert "<lecture_notes>" in msgs[1]["content"]
        assert "INSUFFICIENT_NOTES" in msgs[0]["content"]

    def test_v1_is_minimal(self):
        msgs = render_messages("v1", "SUMMARY", NOTES, "x")
        assert "##" not in msgs[1]["content"]


# ------------------------------------------------------------ formatter ---
class TestFormatter:
    def setup_method(self):
        self.pack = build_study_pack({"SUMMARY": FIXTURE_SUMMARY, "QUESTIONS": FIXTURE_QUESTIONS,
                                      "REVISION": FIXTURE_REVISION})

    def test_sections_parsed(self):
        p = self.pack
        assert p.main_topic.startswith("Binary search")
        assert "halves" in p.summary
        assert p.key_concepts.count("**") == 6
        assert "Worst case" in p.revision_points
        assert p.checklist.startswith("- [ ]")
        assert "Missing" in p.coverage

    def test_questions_parsed(self):
        qs = self.pack.questions
        assert len(qs) == 5
        assert qs[0].qtype == "Factual" and qs[1].qtype == "Conceptual"
        assert qs[0].answer == "Answer 1." and qs[0].evidence.startswith("Each comparison")
        assert qs[4].placeholder and not qs[3].placeholder

    def test_evidence_verification(self):
        ev = verify_evidence(self.pack, NOTES)
        found = {e["Location"]: e["Found in notes"] for e in ev}
        assert found["Concept: Sorted input"] is True
        assert found["Concept: Made up"] is False
        assert found["Q1"] is True

    def test_quote_match_ignores_case_and_punctuation(self):
        assert check_quote("each comparison HALVES the search-space", NOTES)
        assert not check_quote("", NOTES)

    def test_insufficient_detected(self):
        p = build_study_pack({t: "INSUFFICIENT_NOTES: shopping list, not lecture notes." for t in TASKS})
        assert p.is_insufficient and "shopping" in p.insufficient["SUMMARY"]

    def test_unstructured_fallback(self):
        p = build_study_pack({"SUMMARY": "Binary search is fast.", "QUESTIONS": "1. What? A: x",
                              "REVISION": "Remember sorting."})
        assert p.summary == "Binary search is fast."
        assert not p.structured["SUMMARY"] and p.questions == []

    def test_markdown_export(self):
        md = to_markdown(self.pack, "Binary Search", "v3", "test-model")
        for h in ("# StudyMate Study Pack — Binary Search", "## Summary", "## Key Concepts",
                  "## Practice Questions", "### Q1.", "## Quick Revision Checklist", "can contain errors"):
            assert h in md


# ------------------------------------------------------------ evaluator ---
class TestEvaluator:
    def test_metrics_on_fixture(self):
        pack = build_study_pack({"SUMMARY": FIXTURE_SUMMARY, "QUESTIONS": FIXTURE_QUESTIONS,
                                 "REVISION": FIXTURE_REVISION})
        m = evaluate_pack(pack, NOTES, "Brief")
        assert m["structure_ok"] and m["question_count"] == 5
        assert m["answered_count"] == 4 and m["grounded_questions"] == 4
        assert m["evidence_quotes"] == 7 and m["evidence_match_rate"] == round(6 / 7, 3)
        assert m["summary_within_limit"] is True

    def test_novel_terms(self):
        assert novel_term_ratio("binary search sorted array", NOTES) == 0.0
        assert novel_term_ratio("heapsort quicksort", NOTES) == 1.0

    def test_duplicates(self):
        md = "- hash table stores key value pairs\n- a hash table stores key-value pairs\n- load factor"
        assert duplicate_bullet_pairs(md) == 1


# ---------------------------------------------------------- ai generator ---
class FakeBadRequest(Exception):
    pass


FakeBadRequest.__name__ = "BadRequestError"


class FakeRateLimit(Exception):
    pass


FakeRateLimit.__name__ = "RateLimitError"


class FakeClient:
    """Stand-in for openai.OpenAI used only to test request handling logic."""

    def __init__(self, behaviour):
        self.calls = []
        self.behaviour = behaviour
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

    def create(self, **params):
        self.calls.append(dict(params))
        return self.behaviour(len(self.calls), params)


def _resp(text="ok", finish="stop"):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=text), finish_reason=finish)],
        usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5))


class TestGenerator:
    msgs = [{"role": "user", "content": "x"}]

    def test_drops_unsupported_param_and_retries(self):
        def beh(n, p):
            if "temperature" in p:
                raise FakeBadRequest("Unsupported parameter: 'temperature'")
            return _resp()
        c = FakeClient(beh)
        s = ag.GenerationSettings(model="m", temperature=0.2, reasoning_effort=None)
        r = ag.call_model(c, self.msgs, s, sleep=lambda _: None)
        assert r.ok and r.dropped_params == ["temperature"] and len(c.calls) == 2

    def test_retries_transient_then_succeeds(self):
        c = FakeClient(lambda n, p: (_ for _ in ()).throw(FakeRateLimit("slow down")) if n < 3 else _resp())
        r = ag.call_model(c, self.msgs, ag.GenerationSettings(), sleep=lambda _: None)
        assert r.ok and len(c.calls) == 3

    def test_quota_error_not_retried(self):
        c = FakeClient(lambda n, p: (_ for _ in ()).throw(FakeRateLimit("insufficient_quota")))
        r = ag.call_model(c, self.msgs, ag.GenerationSettings(), sleep=lambda _: None)
        assert not r.ok and "quota" in r.error and len(c.calls) == 1

    def test_empty_response_with_length_limit(self):
        c = FakeClient(lambda n, p: _resp("", "length"))
        r = ag.call_model(c, self.msgs, ag.GenerationSettings())
        assert not r.ok and "OPENAI_MAX_OUTPUT_TOKENS" in r.error

    def test_generate_pack_runs_three_tasks(self):
        c = FakeClient(lambda n, p: _resp("text"))
        res = ag.generate_study_pack(NOTES, "s", "v2", client=c,
                                     settings=ag.GenerationSettings(model="m"))
        assert set(res.tasks) == set(TASKS) and res.ok and len(c.calls) == 3
        assert all(call["model"] == "m" for call in c.calls)

    def test_placeholder_key_is_ignored(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-your-key-here")
        assert ag.get_api_key() is None


# ------------------------------------------------- evaluation runner -------
def test_runner_pipeline_with_stub_client(tmp_path, monkeypatch):
    """Exercise run_evaluation.py end to end with a stub client in a temp folder.

    Checks the plumbing only (files written, checks applied, CSV merged). The
    stub returns the hand-written fixtures above; nothing here is an AI result.
    """
    import shutil
    import pandas as pd
    import run_evaluation as rev

    tests_dir = tmp_path / "tests"
    shutil.copytree(rev.INPUTS_DIR, tests_dir / "inputs")
    shutil.copy(rev.CASES_FILE, tests_dir / "test_cases.json")
    monkeypatch.setattr(rev, "ROOT", tmp_path)
    monkeypatch.setattr(rev, "INPUTS_DIR", tests_dir / "inputs")
    monkeypatch.setattr(rev, "OUTPUTS_DIR", tests_dir / "outputs")
    monkeypatch.setattr(rev, "CASES_FILE", tests_dir / "test_cases.json")
    monkeypatch.setattr(rev, "RESULTS_CSV", tests_dir / "evaluation_results.csv")

    def beh(n, p):
        user = p["messages"][1]["content"]
        if "Practice Questions" in user or "practice questions" in user:
            return _resp(FIXTURE_QUESTIONS.replace("### Q5. Not enough information in the notes for another question.",
                                                   '### Q5. (Factual) Q5?\n**Answer:** A5.\n**Evidence:** "x"'))
        if "Revision Points" in user or "revision points" in user:
            return _resp(FIXTURE_REVISION)
        return _resp(FIXTURE_SUMMARY)

    monkeypatch.setattr(rev, "get_api_key", lambda *a: "sk-test")
    monkeypatch.setattr(rev, "make_client", lambda *a: FakeClient(beh))

    assert rev.main(["--tests", "TC01", "TC09", "--versions", "v3"]) == 0
    df = pd.read_csv(tests_dir / "evaluation_results.csv", keep_default_na=False)
    row = df[(df.test_id == "TC01") & (df.prompt_version == "v3")].iloc[0]
    assert row.result == "PASS" and str(row.question_count) == "5"
    assert (tmp_path / row.actual_output_file).exists()
    assert df[df.test_id == "TC09"].iloc[0].result == "PASS"
    assert set(df[df.test_id == "TC02"].result) == {"NOT RUN"}

    # Re-running a different test must keep the TC01 row (merge, not overwrite).
    assert rev.main(["--tests", "TC12", "--versions", "v3"]) == 0
    df2 = pd.read_csv(tests_dir / "evaluation_results.csv", keep_default_na=False)
    assert df2[(df2.test_id == "TC01") & (df2.prompt_version == "v3")].iloc[0].result == "PASS"
    assert len(df2) == len(df)
