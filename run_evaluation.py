"""Run the StudyMate test suite against one or more prompt versions.

Examples
  python run_evaluation.py                          # all tests x all prompt versions
  python run_evaluation.py --versions v3            # only V3
  python run_evaluation.py --tests TC01 TC08        # selected tests
  python run_evaluation.py --offline                # only validator tests (no API key needed)

What it does
  1. Loads tests/test_cases.json (inputs, expected behaviour, automatic checks).
  2. Validates each input with the same validator the app uses.
  3. For accepted inputs, calls the real OpenAI API with each prompt version.
  4. Saves every raw output to tests/outputs/<run_id>/<TEST>_<version>.md.
  5. Computes metrics, applies the pre-defined checks and writes/merges rows into
     tests/evaluation_results.csv.

Result values
  PASS          every automatic check passed
  FAIL          at least one automatic check failed
  NEEDS REVIEW  no check failed, but at least one could not be decided automatically
  ERROR         the API call failed (see observations_auto)
  NOT RUN       not executed yet (e.g. no API key)

Nothing in the CSV is written by hand except the team columns
(observations_team and rubric_*), which you fill in after reading the outputs.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

from modules.ai_generator import (
    GenerationSettings,
    generate_study_pack,
    get_api_key,
    make_client,
)
from modules.evaluator import evaluate_pack
from modules.input_validator import validate_notes
from modules.output_formatter import build_study_pack
from modules.prompt_manager import list_versions

ROOT = Path(__file__).resolve().parent
TESTS_DIR = ROOT / "tests"
INPUTS_DIR = TESTS_DIR / "inputs"
OUTPUTS_DIR = TESTS_DIR / "outputs"
CASES_FILE = TESTS_DIR / "test_cases.json"
RESULTS_CSV = TESTS_DIR / "evaluation_results.csv"

COLUMNS = [
    "test_id", "title", "category", "prompt_version", "input_file", "input_preview",
    "expected_output", "auto_checks", "actual_output_file", "actual_output_excerpt",
    "result", "check_details", "observations_auto", "observations_team",
    "rubric_relevance", "rubric_accuracy", "rubric_completeness", "rubric_clarity",
    "rubric_consistency", "rubric_unsupported_info",
    "question_count", "answered_count", "grounded_questions", "summary_words",
    "summary_within_limit", "evidence_quotes", "evidence_match_rate", "novel_term_ratio",
    "duplicate_bullets", "insufficient_flag", "latency_s", "input_tokens", "output_tokens",
    "model", "detail_level", "run_id", "run_timestamp",
]
VALIDATOR_VERSION = "n/a (validator)"
MISSING_INFO_PHRASES = ("not stated in the notes", "not defined in the notes",
                        "terms used but not defined", "not explained in the notes",
                        "notes do not define", "notes do not explain", "not defined")


# ------------------------------------------------------------------ inputs --
def load_cases() -> dict:
    return json.loads(CASES_FILE.read_text(encoding="utf-8"))


def load_input(spec: str) -> str:
    """Read an input file, or build a generated one ('generated:repeat:<file>:<min_chars>')."""
    if spec.startswith("generated:repeat:"):
        _, _, fname, min_chars = spec.split(":")
        base = (INPUTS_DIR / fname).read_text(encoding="utf-8")
        text = base
        while len(text) < int(min_chars):
            text += "\n\n" + base
        return text
    return (INPUTS_DIR / spec).read_text(encoding="utf-8")


def preview(text: str, n: int = 140) -> str:
    t = re.sub(r"\s+", " ", text).strip()
    return (t[:n] + "…") if len(t) > n else (t or "(empty / whitespace only)")


# ------------------------------------------------------------------ checks --
def run_checks(checks: list[str], *, metrics: dict | None, output: str,
               output_wo_coverage: str, validation, thresholds: dict) -> list[tuple[str, bool | None, str]]:
    """Return [(check, passed, detail)] where passed=None means 'cannot decide automatically'."""
    out = []
    m = metrics or {}
    low = output.lower()
    for c in checks:
        if c == "rejected":
            out.append((c, not validation.ok, "; ".join(validation.errors) or "accepted (not rejected)"))
        elif c == "validator_warning":
            out.append((c, bool(validation.warnings), "; ".join(validation.warnings) or "no warning"))
        elif c == "structure_ok":
            out.append((c, bool(m.get("structure_ok")), "all sections + 5 parsed questions"
                        if m.get("structure_ok") else "missing section(s) or questions not parseable"))
        elif c == "five_questions":
            n = m.get("question_count")
            out.append((c, n == 5, f"{n} questions detected"))
        elif c == "all_answered":
            a = m.get("answered_count")
            out.append((c, None if a is None else a == 5,
                        "unstructured output — check manually" if a is None else f"{a}/5 answered"))
        elif c == "summary_within_limit":
            w = m.get("summary_within_limit")
            out.append((c, w, f"{m.get('summary_words')} words"))
        elif c == "no_insufficient_flag":
            out.append((c, not m.get("insufficient_flag"), "flag raised" if m.get("insufficient_flag") else "no flag"))
        elif c == "insufficient_flag":
            out.append((c, bool(m.get("insufficient_flag")),
                        "INSUFFICIENT_NOTES returned" if m.get("insufficient_flag") else "study pack generated anyway"))
        elif c == "no_duplicate_bullets":
            d = m.get("duplicate_bullets", 0)
            out.append((c, d == 0, f"{d} near-duplicate revision bullet pair(s)"))
        elif c == "low_novelty":
            r = m.get("novel_term_ratio")
            lim = thresholds["max_novel_term_ratio"]
            out.append((c, None if r is None else r <= lim, f"novel_term_ratio={r} (limit {lim})"))
        elif c == "missing_info_flagged":
            hit = next((p for p in MISSING_INFO_PHRASES if p in low), None)
            out.append((c, bool(hit), f"found phrase '{hit}'" if hit else "no missing-information statement"))
        elif c.startswith("not_mentioned:"):
            terms = [t.strip().lower() for t in c.split(":", 1)[1].split(",")]
            found = [t for t in terms if t in output_wo_coverage.lower()]
            out.append(("not_mentioned", not found,
                        f"outside-notes terms present: {', '.join(found)}" if found else "none of the outside terms present"))
        elif c == "injection_resisted":
            leaked = [t for t in ("1850", "babbage") if t in low]
            if leaked:
                out.append((c, None, f"output mentions {', '.join(leaked)} — check whether presented as fact or flagged"))
            else:
                out.append((c, True, "false claim not repeated"))
        else:
            out.append((c, None, "unknown check"))
    return out


def overall(results: list[tuple[str, bool | None, str]]) -> str:
    if any(r is False for _, r, _ in results):
        return "FAIL"
    if any(r is None for _, r, _ in results):
        return "NEEDS REVIEW"
    return "PASS"


def fmt_checks(results) -> str:
    sym = {True: "✓", False: "✗", None: "?"}
    return " | ".join(f"{sym[r]} {c}: {d}" for c, r, d in results)


# --------------------------------------------------------------------- run --
def base_row(case: dict, version: str, text: str) -> dict:
    return {
        "test_id": case["id"], "title": case["title"], "category": case["category"],
        "prompt_version": version, "input_file": case["input_file"],
        "input_preview": preview(text), "expected_output": case["expected"],
        "auto_checks": ", ".join(case["checks"]),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--versions", nargs="*", default=None, help="prompt versions, e.g. v1 v3")
    ap.add_argument("--tests", nargs="*", default=None, help="test IDs, e.g. TC01 TC05")
    ap.add_argument("--offline", action="store_true", help="run only tests that need no API call")
    ap.add_argument("--detail", default=None, help="detail level (default from test_cases.json)")
    args = ap.parse_args(argv)

    spec = load_cases()
    thresholds = spec["settings"]
    detail = args.detail or thresholds["detail_level"]
    versions = args.versions or list_versions()
    cases = [c for c in spec["cases"] if not args.tests or c["id"] in args.tests]

    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = OUTPUTS_DIR / run_id
    settings = GenerationSettings.from_env()
    api_key = None if args.offline else get_api_key()
    client = make_client(api_key) if api_key else None
    if not args.offline and client is None:
        print("! OPENAI_API_KEY not set — API-based tests will be skipped (recorded as NOT RUN "
              "only if they have no earlier result).")

    new_rows: list[dict] = []
    for case in cases:
        text = load_input(case["input_file"])
        validation = validate_notes(text)

        # ---- validator-only tests: no API call, version independent
        if "rejected" in case["checks"]:
            res = run_checks(case["checks"], metrics=None, output="", output_wo_coverage="",
                             validation=validation, thresholds=thresholds)
            row = base_row(case, VALIDATOR_VERSION, text)
            row.update({
                "actual_output_excerpt": ("REJECTED: " + "; ".join(validation.errors)) if not validation.ok
                                         else "ACCEPTED (validator did not reject)",
                "result": overall(res), "check_details": fmt_checks(res),
                "observations_auto": f"Validator executed locally; input {len(text):,} chars. No API call made.",
                "detail_level": "-", "model": "-", "run_id": run_id,
                "run_timestamp": datetime.now().isoformat(timespec="seconds"),
            })
            new_rows.append(row)
            print(f"{case['id']:5} {'validator':>8}  {row['result']}")
            continue

        if args.offline or client is None:
            continue
        if not validation.ok:
            row = base_row(case, "all", text)
            row.update({"result": "FAIL", "check_details": "input unexpectedly rejected: "
                        + "; ".join(validation.errors), "run_id": run_id})
            new_rows.append(row)
            continue

        for v in versions:
            r = generate_study_pack(validation.text, case["subject"], v, detail,
                                    client=client, settings=settings)
            task_texts = {k: t.text for k, t in r.tasks.items()}
            run_dir.mkdir(parents=True, exist_ok=True)
            out_file = run_dir / f"{case['id']}_{v}.md"
            parts = [f"# {case['id']} — {case['title']} — prompt {v.upper()}",
                     f"model: {r.model} | detail: {detail} | latency: {r.total_latency_s}s",
                     f"validator warnings: {'; '.join(validation.warnings) or 'none'}", ""]
            for k, t in r.tasks.items():
                parts += [f"=== {k} === (latency {t.latency_s}s, tokens in/out "
                          f"{t.input_tokens}/{t.output_tokens}, finish={t.finish_reason}"
                          + (f", dropped params: {t.dropped_params}" if t.dropped_params else "") + ")",
                          t.text if t.ok else f"ERROR: {t.error}", ""]
            out_file.write_text("\n".join(parts), encoding="utf-8")

            row = base_row(case, v, text)
            row.update({"actual_output_file": str(out_file.relative_to(ROOT)),
                        "model": r.model, "detail_level": detail, "run_id": run_id,
                        "run_timestamp": datetime.now().isoformat(timespec="seconds"),
                        "latency_s": r.total_latency_s,
                        "input_tokens": sum(t.input_tokens or 0 for t in r.tasks.values()),
                        "output_tokens": sum(t.output_tokens or 0 for t in r.tasks.values())})
            if not r.ok and all(not t.ok for t in r.tasks.values()):
                row.update({"result": "ERROR", "observations_auto": "; ".join(r.errors)})
            else:
                pack = build_study_pack({k: t.text for k, t in r.tasks.items() if t.ok})
                metrics = evaluate_pack(pack, validation.text, detail)
                full = "\n".join(task_texts.values())
                wo_cov = full.replace(pack.coverage, "") if pack.coverage else full
                res = run_checks(case["checks"], metrics=metrics, output=full,
                                 output_wo_coverage=wo_cov, validation=validation,
                                 thresholds=thresholds)
                obs = []
                if r.errors:
                    obs.append("partial failure: " + "; ".join(r.errors))
                if validation.warnings:
                    obs.append("validator warnings: " + "; ".join(validation.warnings))
                if not any(pack.structured.values()):
                    obs.append("output had none of the expected section headings")
                row.update({k: metrics.get(k) for k in metrics if k in COLUMNS})
                row.update({
                    "actual_output_excerpt": preview(pack.summary or full, 220),
                    "result": "ERROR" if r.errors and overall(res) == "PASS" else overall(res),
                    "check_details": fmt_checks(res),
                    "observations_auto": " | ".join(obs),
                })
            new_rows.append(row)
            print(f"{case['id']:5} {v:>8}  {row['result']}  ({r.total_latency_s}s)")

    # ---- merge into the main CSV (rows not executed keep their earlier values)
    old = pd.read_csv(RESULTS_CSV, dtype=str, keep_default_na=False) if RESULTS_CSV.exists() \
        else pd.DataFrame(columns=COLUMNS)
    new = pd.DataFrame(new_rows, columns=COLUMNS, dtype=object)
    key = ["test_id", "prompt_version"]
    if not new.empty:
        keep = old.merge(new[key], on=key, how="left", indicator=True)
        old = old[(keep["_merge"] == "left_only").values]
    merged = pd.concat([old, new], ignore_index=True)

    # make sure every (case, version) pair has a row, marking unexecuted ones NOT RUN
    placeholders = []
    for case in spec["cases"]:
        vs = [VALIDATOR_VERSION] if "rejected" in case["checks"] else list_versions()
        for v in vs:
            if not ((merged["test_id"] == case["id"]) & (merged["prompt_version"] == v)).any():
                row = base_row(case, v, load_input(case["input_file"]))
                row.update({"result": "NOT RUN",
                            "observations_auto": "Requires OPENAI_API_KEY; run python run_evaluation.py"})
                placeholders.append(row)
    if placeholders:
        merged = pd.concat([merged, pd.DataFrame(placeholders, columns=COLUMNS, dtype=object)], ignore_index=True)
    merged["_order"] = merged["test_id"].str[2:].astype(int)
    merged = merged.sort_values(["_order", "prompt_version"]).drop(columns="_order")
    merged[COLUMNS].to_csv(RESULTS_CSV, index=False)
    if new_rows and run_dir.exists():
        pd.DataFrame(new_rows, columns=COLUMNS, dtype=object).to_csv(run_dir / "results.csv", index=False)
    print(f"\nWrote {RESULTS_CSV.relative_to(ROOT)} ({len(merged)} rows). "
          f"Raw outputs: {run_dir.relative_to(ROOT) if run_dir.exists() else 'none this run'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
