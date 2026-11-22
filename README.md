# StudyMate — AI-Powered Study Pack Generator

> Turn your lecture notes into smarter revision.

StudyMate turns lecture notes into a structured study pack: summary, key concepts, five practice questions with answers, revision points and a quick revision checklist. All content is kept grounded in the notes the student provides.

It was built for the **Prompt Engineering** course at **Bennett University** (Milestone 2, Problem Pool **C2 — Lecture Notes to Study Pack**) by team **Promptly Unemployed**. The focus of the project is the prompt design: three iterated prompt versions, a side-by-side comparison tool and a reproducible evaluation over 12 test cases.

---

## Problem statement

Students revising long lecture notes before exams spend a lot of time writing summaries, picking out key concepts and making practice questions. General-purpose chatbots can do this, but they mix in outside facts, change format from run to run, and may invent content when the notes are thin. StudyMate uses engineered prompts to produce consistent, structured study material that stays within the student's own notes and says clearly when information is missing.

## Features

- **Notes input:** paste text or upload a `.txt` file, add a subject, choose Brief / Standard / Detailed. Empty and over-length input is blocked before any API call. Warnings for very short notes and apparent personal data.
- **Three prompt tasks:** A. Summary (main topic, summary, key concepts), B. Practice Questions (exactly 5, factual and conceptual, with answers), C. Revision (points, definitions, checklist, source coverage). They run in parallel.
- **Structured display:** tabs for Summary, Key Concepts, Practice Questions (answers behind "Show answer"), Revision Points, Verification and Copy. Download as `.md` or `.txt`.
- **Grounding and verification (V3):** notes-only rules, "Not stated in the notes" for gaps, an `INSUFFICIENT_NOTES` response for non-study input, prompt-injection defence, and verbatim evidence quotes that the app checks against your notes.
- **Prompt versions V1 → V2 → V3:** selectable in the UI, stored as plain text in `prompts/`.
- **Compare prompts page:** run the same notes through several versions side by side with automatic metrics.
- **Evaluation runner:** 12 test cases × prompt versions, raw outputs saved, results written to CSV.

## Technology stack

| Purpose | Technology |
|---|---|
| Language | Python 3.10+ |
| UI | Streamlit (custom CSS, black/white/grey theme) |
| AI model | OpenAI API — Chat Completions (default `gpt-5.4-mini`, configurable) |
| Secrets | python-dotenv (`.env`) or Streamlit secrets |
| Evaluation | pandas, matplotlib, pytest |
| Diagrams | Graphviz (`docs/diagrams/*.dot`) |
| Version control | Git / GitHub |

## Installation (macOS)

```bash
# 1. Get the code
git clone https://github.com/<your-org>/StudyMate.git
cd StudyMate

# 2. Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Add your OpenAI API key
cp .env.example .env
open -e .env        # set OPENAI_API_KEY=sk-...
```

Python 3.10 or newer is required (`python3 --version`). If it's missing, install it from python.org or with `brew install python`.

### Environment variables

| Variable | Required | Default | Meaning |
|---|---|---|---|
| `OPENAI_API_KEY` | yes | — | Your OpenAI key (platform.openai.com → API keys). The account needs billing/credit. |
| `OPENAI_MODEL` | no | `gpt-5.4-mini` | Any chat model your key can use |
| `OPENAI_TEMPERATURE` | no | blank | Leave blank for reasoning models |
| `OPENAI_REASONING_EFFORT` | no | `low` | Ignored automatically by models that don't support it |
| `OPENAI_MAX_OUTPUT_TOKENS` | no | `4000` | Per task, including reasoning tokens |

The `.env` file is in `.gitignore`. **Never commit your key.** You can also paste a key into the sidebar for the current browser session only.

## How to run

```bash
streamlit run app.py
```

The app opens at http://localhost:8501. Choose **Try a sample → Binary search** and click **Generate Study Pack**.

### Run the tests and experiments

```bash
python -m pytest -q          # 41 offline unit/integration tests (no key needed)
python run_evaluation.py     # 12 test cases × V1, V2, V3 against the real API (~90 calls)
python summarize_results.py  # writes docs/evaluation_summary.md and a chart
```

See [`docs/testing_methodology.md`](docs/testing_methodology.md) for the checks, metrics and human rubric.

## Prompt engineering summary

| Version | Idea | Main additions |
|---|---|---|
| V1 Baseline | Control condition | One plain instruction per task |
| V2 Structured | Consistency | Role, exact headings, word/item limits, exactly 5 labelled Q&As |
| V3 Grounded | Reliability | Notes-only rules, delimited notes, missing-info statements, `INSUFFICIENT_NOTES`, evidence quotes, no padding or repetition, source coverage, self-check |

Full rationale: [`docs/prompt_iteration_log.md`](docs/prompt_iteration_log.md). Measured results: [`docs/evaluation_summary.md`](docs/evaluation_summary.md) (generated from real runs).

## Screenshots

Add real screenshots of the running app to `screenshots/` and link them here, for example:

```markdown
![Generate page](screenshots/01_generate.png)
![Study pack](screenshots/02_results.png)
![Compare prompts](screenshots/03_compare.png)
```

## Project structure

```
app.py · run_evaluation.py · summarize_results.py · requirements.txt · .env.example
prompts/   prompt_v1.txt  prompt_v2.txt  prompt_v3.txt
modules/   input_validator.py  prompt_manager.py  ai_generator.py  output_formatter.py  evaluator.py
tests/     inputs/  outputs/  test_cases.json  test_cases.md  evaluation_results.csv  test_modules.py
docs/      architecture.md  prompt_iteration_log.md  testing_methodology.md  demo_script.md  diagrams/
screenshots/
```

Details: [`docs/architecture.md`](docs/architecture.md).

## Responsible AI

- Notes are sent to an **external AI model (OpenAI)**. Don't upload confidential or personally identifiable material. The app warns when it detects emails or phone numbers.
- Generated content **may contain errors**. Always check answers against your original notes.
- V3 restricts output to the notes, labels missing information, and treats instructions inside the notes as data.
- The Verification tab shows whether evidence quotes appear in the notes. That is a grounding signal, **not** a guarantee of correctness.

## Limitations

- Plain text only (no PDF/PPTX parsing yet); 40,000-character limit per request.
- Automatic metrics are proxies; quality judgements need human review.
- Outputs vary between runs; results depend on the chosen model.
- The evidence check is exact string matching, so a quote with a small change counts as not found.

## Future scope

- PDF / slide upload with text extraction, and chunking for whole-semester notes
- Interactive quiz mode with scoring and spaced repetition
- Model-graded (LLM-as-judge) evaluation alongside human scores
- Export to Anki flashcards
- Multilingual notes (Hindi and English)

## Team

Promptly Unemployed, Bennett University. Member names and contributions: see the Milestone 2 report.
