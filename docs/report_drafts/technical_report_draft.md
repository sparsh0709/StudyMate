# StudyMate — Supporting Technical Report (DRAFT)

> Sections marked «TO FILL» need real results. Everything else describes what is implemented and tested in the repository.

## 1. Abstract
StudyMate is a web application that turns university lecture notes into structured study packs: a summary, key concepts, five practice questions with answers, revision points and a checklist. It uses OpenAI's language model through three independent, engineered prompt tasks. We designed three prompt versions — a plain baseline (V1), a structured prompt (V2) and a grounded, quality-controlled prompt (V3) — and evaluated them on twelve test cases covering normal, long, short, repetitive, incomplete, empty, irrelevant and adversarial inputs, using automatic checks and a human rubric. «TO FILL: one or two sentences with the main measured findings.»

## 2. Problem Statement
Revising from long lecture notes is time-consuming. Students need condensed summaries and self-test questions, but writing them by hand takes hours. General-purpose AI assistants can produce such material, but with three problems for exam revision: (1) inconsistent structure and length, (2) content that is not in the student's notes (outside facts or hallucinations), presented with the same confidence as the notes, and (3) no indication when the notes are incomplete.

## 3. Objectives
1. Build a working, demonstrable web application that generates a study pack from user-supplied notes.
2. Design and iterate at least three prompt versions, each targeting documented weaknesses.
3. Keep generated content grounded in the supplied notes and make missing information explicit.
4. Evaluate versions on a fixed test set with pre-defined pass criteria, reporting failures honestly.
5. Apply responsible-AI safeguards (disclosure, verification advice, personal-data warnings, injection resistance).

## 4. System Architecture
Insert `docs/diagrams/architecture.png` and `docs/diagrams/workflow.png`. Describe the presentation layer (Streamlit `app.py`), application layer (five modules), data/external layer (prompt files, `.env`, OpenAI API) and offline evaluation (`run_evaluation.py`, `summarize_results.py`), using `docs/architecture.md`.

## 5. Technology Stack
| Component | Choice | Reason |
|---|---|---|
| Language | Python 3.10+ | Course standard; strong AI/data ecosystem |
| UI | Streamlit | Fast to build interactive data apps in pure Python; customised with CSS |
| Model | OpenAI Chat Completions, «TO FILL: model» | Reliable instruction following; low cost per study pack |
| Config | python-dotenv | Keeps keys out of code |
| Evaluation | pandas, matplotlib, pytest | Reproducible tables, charts and tests |
| Diagrams | Graphviz | Diagrams kept as source files |

## 6. Prompt Architecture
- One **system message** per version (role, style, and in V3 the grounding rules).
- Three **task prompts** (SUMMARY, QUESTIONS, REVISION) sharing the notes but with separate output contracts.
- **Placeholders** filled at runtime; the **detail level** maps to numeric limits (Brief 80–120 / Standard 150–200 / Detailed 250–300 summary words; concept, point and checklist counts).
- **Output contract:** fixed Markdown headings and a Q/A pattern, parsed by `output_formatter.py`.
- **Grounding contract (V3):** delimited notes, notes-only rule, "Not stated in the notes", `INSUFFICIENT_NOTES`, verbatim evidence quotes checked locally.

## 7. Prompt Iteration History
Summarise `docs/prompt_iteration_log.md`: the hypothesised V1 weaknesses (W1–W6), the V1→V2 and V2→V3 change tables, and the risks V3 introduces (over-refusal, padding conflict, non-verbatim quotes, token cost). «TO FILL: the experiment record table with real run IDs and observations, and any V4 iteration.»

## 8. Testing Methodology
Summarise `docs/testing_methodology.md`: three testing levels, the 12 test cases, controlled conditions, automatic checks, metric limitations, and the human rubric with independent scoring.

## 9. Actual Test Results
«TO FILL from `docs/evaluation_summary.md` after running `python run_evaluation.py` and `python summarize_results.py`:»
- Result matrix (12 tests × V1/V2/V3)
- PASS / FAIL / NEEDS REVIEW counts per version
- Mean automatic metrics per version (+ chart)
- Mean rubric scores per version and the number of raters
- Failure analysis: each failure, its cause, and whether a later version fixed it

Executed so far: TC09 (empty) and TC11 (over-length) PASS. Both were rejected by the validator before any API call. Unit/integration suite: 41/41 tests passing.

## 10. Limitations
- Automatic metrics are proxies: `novel_term_ratio` counts synonyms as novel; the evidence check confirms a quote exists, not that the claim is correct.
- Each test was run once per version «TO FILL: or N times»; model output varies between runs.
- Small test set (12 cases), written by the team, mostly computer-science topics.
- Text-only input with a 40,000-character limit; no PDF or slide parsing.
- Results depend on the model and its version; a model update can change behaviour.
- Rubric scores come from team members who know the project, which may introduce bias.

## 11. Responsible AI Considerations
- **Transparency:** the UI and downloads state that content is generated by an external AI model and may contain errors.
- **Privacy:** notes are sent to OpenAI; the app warns about emails and phone numbers and advises against confidential material; API keys stay local.
- **Grounding and honesty:** V3 restricts content to the notes, labels missing information, and returns `INSUFFICIENT_NOTES` instead of inventing content.
- **Security:** notes are delimited and treated as data to reduce prompt-injection risk (tested in TC12).
- **Academic integrity:** StudyMate supports revision; it does not replace studying the original material, and students should verify answers.
- **Evaluation integrity:** no fabricated outputs or scores; pass criteria fixed before testing; failures reported.

## 12. Conclusion
«TO FILL after results: what the experiments showed about structure (V2) and grounding (V3), what still fails, and what you would do next.»

## 13. References
1. OpenAI. *API documentation — Chat Completions and models.* https://platform.openai.com/docs
2. OpenAI. *Prompt engineering guide.* https://platform.openai.com/docs/guides/prompt-engineering
3. Streamlit. *Documentation.* https://docs.streamlit.io
4. Wei, J. et al. (2022). *Chain-of-Thought Prompting Elicits Reasoning in Large Language Models.* NeurIPS.
5. Ji, Z. et al. (2023). *Survey of Hallucination in Natural Language Generation.* ACM Computing Surveys 55(12).
6. Greshake, K. et al. (2023). *Not what you've signed up for: Compromising Real-World LLM-Integrated Applications with Indirect Prompt Injection.* AISec '23.
7. «TO FILL: course material / any other sources you used»
