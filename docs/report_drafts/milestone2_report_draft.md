# Milestone 2 Report — DRAFT

> **How to use this draft:** sections marked «TO FILL» need real results, screenshots or team details. Check the section order against the official Milestone 2 instructions before exporting to PDF. Delete this box before submitting.

---

## 1. Cover Page

**StudyMate — AI-Powered Study Pack Generator**

| | |
|---|---|
| Course | Prompt Engineering |
| University | Bennett University |
| Milestone | 2 — Prompt Design, Experimentation, Implementation and Demonstration |
| Problem Pool | C2 — Lecture Notes to Study Pack |
| Team | Promptly Unemployed |
| Members | «TO FILL: Name — Enrolment No.» × 4 |
| Faculty | «TO FILL» |
| Repository | «TO FILL: GitHub URL» |
| Date | 22 November 2026 |

---

## 2. Prompt and Solution Design

### 2.1 Problem and objective
Students revising long lecture notes need concise summaries, key concepts and practice questions. Generic chatbot output changes format between runs and may add information that isn't in the student's notes. StudyMate's objective is to show how prompt engineering improves the **relevance, consistency and grounding** of AI-generated study material.

### 2.2 Solution overview
A Streamlit web app sends the student's notes through **three independent prompt tasks**:

- **A. Summary Generator:** main topic, length-controlled summary, key concepts.
- **B. Practice Question Generator:** exactly five questions (factual and conceptual) with answers.
- **C. Revision Generator:** revision points, definitions, quick checklist (and source coverage in V3).

Insert `docs/diagrams/workflow.png`.

### 2.3 Prompt architecture
Each prompt version is a plain-text file with a shared SYSTEM section and three task sections, rendered with placeholders (`{{NOTES}}`, `{{SUBJECT}}`, `{{DETAIL_LEVEL}}`, `{{SUMMARY_WORDS}}`, …). Insert `docs/diagrams/prompt_evolution.png`.

### 2.4 Prompt versions
- **V1 — Baseline:** one plain instruction per task. *Excerpt:* "Summarize these lecture notes about {{SUBJECT}} and explain the key concepts."
- **V2 — Structured:** role and audience, exact headings, word/item limits by detail level, exactly 5 labelled Q&As in a fixed pattern.
- **V3 — Grounded and Quality-Controlled:** notes-only grounding rules that override everything else; notes in `<lecture_notes>` tags treated as data; "Not stated in the notes"; `INSUFFICIENT_NOTES`; ≤12-word verbatim evidence quotes; no padding or repetition; source coverage; silent self-check.

Include the full prompt text from `prompts/prompt_v1.txt`, `prompt_v2.txt` and `prompt_v3.txt` as an appendix or in this section, plus the change table from `docs/prompt_iteration_log.md`.

### 2.5 Design rationale
Summarise the key design decisions from `docs/architecture.md` (three tasks, prompts as files, Markdown headings rather than JSON, locally checkable evidence, validation before the API).

---

## 3. Implementation

### 3.1 Technology stack
Python · Streamlit · OpenAI Chat Completions API (model: «TO FILL: model actually used, e.g. gpt-5.4-mini») · python-dotenv · pandas · matplotlib · pytest · Git/GitHub.

### 3.2 System architecture
Insert `docs/diagrams/architecture.png`. One paragraph per module (see the table in `docs/architecture.md`).

### 3.3 Key features implemented
Notes input with validation · three parallel prompt tasks · tabbed display · Markdown/TXT download and copy · prompt version selector · Compare prompts page · Verification tab with evidence checking · responsible-AI warnings.

### 3.4 Implementation screenshots
«TO FILL: real screenshots of your own run»
1. Generate page (empty)
2. Study pack: Summary tab
3. Practice Questions with an answer expanded
4. Verification tab
5. Compare prompts page with the metrics table
6. Error handling (empty input message)

---

## 4. Demonstration and Testing

### 4.1 Testing approach
Three levels: (1) 41 automated unit/integration tests, (2) 12 test cases × 3 prompt versions against the real API, (3) human rubric scoring. Pass criteria were fixed before testing (see `docs/testing_methodology.md`).

### 4.2 Test cases
Insert the table from `tests/test_cases.md`.

### 4.3 Results
«TO FILL from `docs/evaluation_summary.md`: result matrix, counts by version, mean metrics, chart `docs/diagrams/metrics_by_version.png`, rubric means.»

Already executed (validator, no API): **TC09 empty input: PASS**, **TC11 over-length input: PASS** (both rejected before any API call with the expected messages).

### 4.4 Analysis and failure cases
«TO FILL: for every FAIL / NEEDS REVIEW, say what happened, why, and whether a later prompt version fixed it. Quote short excerpts from `tests/outputs/<run_id>/`. Only state that V3 outperforms V2 or V1 where the numbers show it.»

### 4.5 Demonstration video
«TO FILL: link to the video (unlisted YouTube or Drive)». Script: `docs/demo_script.md`.

---

## 5. Repository

- URL: «TO FILL»
- Structure: see the README "Project structure" section
- How to run: `pip install -r requirements.txt` → `cp .env.example .env` → `streamlit run app.py`
- Evidence in the repo: `tests/evaluation_results.csv`, `tests/outputs/`, `docs/evaluation_summary.md`

---

## 6. Supporting Document

The separate Supporting Technical Report (PDF) covers the abstract, architecture, prompt iteration history, methodology, full results, limitations and responsible AI considerations. «TO FILL: file name / link»

---

## 7. Team Contribution

| Member | Role | Contributions |
|---|---|---|
| «TO FILL» | | |
| «TO FILL» | | |
| «TO FILL» | | |
| «TO FILL» | | |

Describe what each member actually did (prompt design, implementation, testing and rubric scoring, documentation, video).
