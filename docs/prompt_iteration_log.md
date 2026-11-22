# Prompt Iteration Log

This log records **what** changed between prompt versions, **why**, **which weakness** each change targets and **what to measure**. It records design intent only. Whether V2 or V3 actually performs better is decided by the experiments in `tests/evaluation_results.csv`, not by this document.

All three versions share the same architecture: one system message and three task prompts (A. SUMMARY, B. QUESTIONS, C. REVISION), stored in `prompts/prompt_vN.txt` and rendered by `modules/prompt_manager.py`.

![Prompt evolution](diagrams/prompt_evolution.png)

---

## V1 — Baseline (`prompts/prompt_v1.txt`)

**Design:** One plain instruction per task, for example *"Summarize these lecture notes about {{SUBJECT}} and explain the key concepts."* The notes are appended directly. No role, format, limits or grounding rules. The detail-level setting is deliberately ignored.

**Purpose:** A control condition. It shows what the model does with no prompt engineering, so V2 and V3 can be compared against it.

**Expected weaknesses (hypotheses to test):**

| ID | Hypothesised weakness | How it would show up |
|---|---|---|
| W1 | Unpredictable structure | Headings differ run to run; the app cannot split output into tabs (`structure_ok = False`) |
| W2 | Uncontrolled length | Summary word count varies widely and ignores the detail level |
| W3 | Question format varies | Answers not clearly separated; question count can't be parsed reliably |
| W4 | Outside knowledge added | Extra facts, algorithms or definitions not in the notes (TC02, TC05, TC08; higher `novel_term_ratio`) |
| W5 | No handling of non-notes input | Builds a pack from the subject name alone when the notes are irrelevant (TC10) |
| W6 | Follows instructions embedded in notes | TC12 prompt injection |

---

## V1 → V2: Structured (`prompts/prompt_v2.txt`)

| Change | Why | Targets | Measure |
|---|---|---|---|
| System role: "StudyMate, an academic study assistant for university students", simple English, no preamble | Sets audience and tone; removes chatty intros and outros | Clarity, noise | Rubric: clarity |
| Exact Markdown headings per task (`## Main Topic`, `## Summary`, `## Key Concepts`, `## Practice Questions`, `## Revision Points`, `## Key Definitions`, `## Quick Revision Checklist`) | The app parses on these headings to fill the tabs; consistency across runs | W1 | `structure_ok`, PASS rate on `structure_ok` check |
| Word and item limits from the detail level (Brief 80–120, Standard 150–200, Detailed 250–300 summary words; concept/point/checklist counts) | Makes length controllable and predictable | W2 | `summary_words`, `summary_within_limit` |
| "EXACTLY 5 questions", ≥2 factual and ≥2 conceptual, labelled `(Factual)` / `(Conceptual)` | Requirement of the brief; a mix tests recall and understanding | W3 | `question_count`, factual/conceptual labels present |
| Fixed Q/A pattern `### Qn. (Type) …` / `**Answer:** …`, 1–3-sentence answers | Machine-parsable; answers can be hidden behind "Show answer" | W3 | `answered_count` |
| Checklist format `- [ ] I can …` | Actionable self-check items | Usability | Rubric: clarity, completeness |

**Not addressed in V2 (on purpose):** grounding (W4), irrelevant input (W5), prompt injection (W6). This isolates the effect of *structure* from the effect of *grounding*.

---

## V2 → V3: Grounded and Quality-Controlled (`prompts/prompt_v3.txt`)

| Change | Why | Targets | Measure |
|---|---|---|---|
| **Grounding rules in the system message**, declared to override all other instructions: use ONLY the notes; no outside facts, examples, formulas, dates, names or definitions | The core requirement: content must stay grounded in the supplied notes | W4 | `novel_term_ratio`, `not_mentioned` checks (TC02, TC08), rubric: unsupported information, accuracy |
| Notes wrapped in `<lecture_notes>` tags, with the rule that text inside is data, not instructions | Separates instructions from untrusted content (prompt-injection defence) | W6 | TC12 `injection_resisted` |
| "Not stated in the notes" phrase for gaps; Revision adds **"Terms used but not defined in the notes"** | Missing information is reported explicitly instead of silently filled in | W4 | TC08 `missing_info_flagged` |
| `INSUFFICIENT_NOTES: <reason>` single-line escape hatch | Lets the model refuse cleanly when the input isn't study material; the app detects it and shows a notice | W5 | TC10 `insufficient_flag` |
| **Evidence quotes**: each key concept and each answer ends with a ≤12-word verbatim quote from the notes | Makes grounding checkable; the app verifies every quote locally (Verification tab) | W4 | `evidence_quotes`, `evidence_match_rate` |
| "Never pad": up to N items; V3 questions use `Not enough information in the notes…` slots when the notes can't support five | Very short notes shouldn't produce invented filler | W4 | TC05 `low_novelty`, `grounded_questions` |
| "Do not repeat the same point"; "no two questions test the same fact" | Notes with repetition otherwise produce repetitive packs | Repetition | TC07 `duplicate_bullets`, rubric: consistency |
| Main Topic based on the notes, even if the typed subject disagrees | Stops the subject field from overriding the notes (e.g. TC10 subject "Data Structures") | W5 | TC10 |
| **Source Coverage** section (covered vs missing/unclear) | Shows students what the notes do *not* cover | Transparency | Rubric: completeness |
| Silent self-check list at the end of each task | Cheap self-verification instruction before answering | All | All checks |

**Risks introduced by V3 (to watch for in testing):**

- **Over-refusal:** may return `INSUFFICIENT_NOTES` or many "Not stated" lines for valid but terse notes (TC05, TC06). Watch `no_insufficient_flag` on normal tests.
- **Conflict with "exactly five questions":** resolved by placeholder slots. Check whether they appear on normal notes, where they would be a failure.
- **Evidence quotes not verbatim:** the model may paraphrase inside quotes. `evidence_match_rate` < 1.0 shows this.
- **Longer prompts → more input tokens and latency.** Compare `input_tokens` and `latency_s` across versions.

---

## Experiment record

Fill this in from real runs only.

| Date | Run ID | Model | Versions | Tests | Key observations | Follow-up change |
|---|---|---|---|---|---|---|
| _yyyy-mm-dd_ | _from tests/outputs/_ | | | | | |

If testing reveals a weakness in V3 that you fix, save it as `prompts/prompt_v4.txt` (the app and runner pick it up automatically), add a V3 → V4 section above, and re-run the same tests. Do not edit V3 in place after it has been evaluated, or the recorded results stop matching the prompt.
