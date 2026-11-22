
"""StudyMate — AI-Powered Study Pack Generator (Streamlit app).

Run with: streamlit run app.py

Pages
  Generate         paste/upload notes -> study pack
  Compare prompts  run the same notes through V1/V2/V3
  About            how it works, prompt files, responsible AI, limitations
"""

from __future__ import annotations

import html
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pandas as pd
import streamlit as st

from modules.ai_generator import (
    GenerationSettings,
    StudyPackResult,
    generate_study_pack,
    get_api_key,
    make_client,
)
from modules.evaluator import evaluate_pack, novel_terms
from modules.input_validator import (
    decode_upload,
    validate_notes,
    validate_subject,
)
from modules.output_formatter import (
    StudyPack,
    build_study_pack,
    to_markdown,
    verify_evidence,
)
from modules.prompt_manager import (
    DEFAULT_DETAIL,
    DETAIL_LEVELS,
    TASK_LABELS,
    TASKS,
    list_versions,
    load_version,
)

ROOT = Path(__file__).resolve().parent
SAMPLES_DIR = ROOT / "tests" / "inputs"

SAMPLE_FILES = {
    "Binary search": "tc01_binary_search.txt",
    "Sorting algorithms": "tc02_sorting.txt",
    "Operating systems — CPU scheduling": "tc03_os_scheduling.txt",
    "Notes with missing definitions (deadlocks)": "tc08_missing_definitions.txt",
}

st.set_page_config(
    page_title="StudyMate",
    page_icon="📘",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ------------------------------------------------------------------ styling --

st.markdown(
    """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

html, body, [class*="css"], .stMarkdown,
.stTextArea textarea, .stTextInput input, button {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont,
    'Segoe UI', sans-serif !important;
}

#MainMenu, footer, [data-testid="stDecoration"] {
    visibility: hidden;
    height: 0;
}

[data-testid="stHeader"] {
    background: transparent;
}

.block-container {
    padding-top: 2.2rem;
    padding-bottom: 4rem;
    max-width: 1180px;
}

.sm-brand {
    display: flex;
    align-items: center;
    gap: .6rem;
}

.sm-logo {
    width: 34px;
    height: 34px;
    border-radius: 9px;
    background: #111;
    color: #fff;
    display: flex;
    align-items: center;
    justify-content: center;
    font-weight: 700;
    font-size: 17px;
}

.sm-word {
    font-size: 1.45rem;
    font-weight: 700;
    letter-spacing: -0.02em;
    color: #111;
}

.sm-hero h1 {
    font-size: 2.35rem;
    font-weight: 700;
    letter-spacing: -0.035em;
    line-height: 1.15;
    margin: 1.6rem 0 .4rem 0;
    color: #111;
}

.sm-hero p {
    color: #6b6b6b;
    font-size: 1.05rem;
    margin: 0 0 1.6rem 0;
}

.sm-label {
    font-size: .72rem;
    font-weight: 600;
    letter-spacing: .08em;
    text-transform: uppercase;
    color: #8a8a8a;
    margin-bottom: .35rem;
}

.sm-muted {
    color: #6b6b6b;
    font-size: .9rem;
}

.sm-badge {
    display: inline-block;
    padding: .12rem .55rem;
    border-radius: 999px;
    font-size: .72rem;
    font-weight: 600;
    border: 1px solid #e3e3e3;
    background: #f6f6f6;
    color: #333;
    margin-right: .35rem;
}

.sm-badge.dark {
    background: #111;
    color: #fff;
    border-color: #111;
}

.sm-q {
    font-weight: 600;
    font-size: 1.0rem;
    color: #111;
    margin: .15rem 0 .2rem 0;
}

.sm-meta {
    display: flex;
    gap: 1.6rem;
    flex-wrap: wrap;
    padding: .2rem 0 .6rem 0;
}

.sm-meta div {
    font-size: .82rem;
    color: #6b6b6b;
}

.sm-meta b {
    display: block;
    color: #111;
    font-size: .95rem;
    font-weight: 600;
}

.sm-note {
    border-left: 3px solid #111;
    background: #f6f6f6;
    padding: .7rem 1rem;
    border-radius: 6px;
    font-size: .88rem;
    color: #333;
    margin: .6rem 0 1rem 0;
}

[data-testid="stVerticalBlockBorderWrapper"] {
    border-radius: 14px !important;
    border-color: #e9e9e9 !important;
    box-shadow: 0 1px 2px rgba(0,0,0,.04),
                0 4px 16px rgba(0,0,0,.03);
    background: #fff;
}

.stButton > button,
.stDownloadButton > button {
    border-radius: 10px;
    font-weight: 600;
    border: 1px solid #d9d9d9;
    padding: .5rem 1rem;
}

.stButton > button[kind="primary"] {
    background: #111;
    border-color: #111;
    color: #fff;
}

.stButton > button[kind="primary"]:hover {
    background: #2b2b2b;
    border-color: #2b2b2b;
}

.stTextArea textarea,
.stTextInput input {
    border-radius: 10px !important;
}

.stTabs [data-baseweb="tab-list"] {
    gap: .4rem;
    border-bottom: 1px solid #ececec;
}

.stTabs [data-baseweb="tab"] {
    font-weight: 600;
    color: #7a7a7a;
    padding: .55rem .9rem;
}

.stTabs [aria-selected="true"] {
    color: #111 !important;
}

.stTabs [data-baseweb="tab-highlight"] {
    background-color: #111 !important;
}

[data-testid="stExpander"] details {
    border-radius: 10px;
    border-color: #ececec;
}
</style>
""",
    unsafe_allow_html=True,
)

# ------------------------------------------------------------ session state --

for key, default in {
    "notes_input": "",
    "subject_input": "",
    "result": None,
    "result_notes": "",
    "compare": None,
    "compare_notes": "",
    "sidebar_key": "",
}.items():
    st.session_state.setdefault(key, default)


# ------------------------------------------------------------- Gemini key --

def secret_key() -> str | None:
    """Read Gemini API key from Streamlit Cloud Secrets."""
    try:
        return st.secrets.get("GEMINI_API_KEY")
    except Exception:
        return None


def active_api_key() -> str | None:
    """Get key from sidebar, Streamlit Secrets or environment."""
    return get_api_key(
        st.session_state.sidebar_key or secret_key()
    )


# ------------------------------------------------------------------ sidebar --

with st.sidebar:
    st.markdown("### Settings")

    env_settings = GenerationSettings.from_env()
    key = active_api_key()

    if key:
        st.success("Gemini API key loaded", icon="🔑")
    else:
        st.warning(
            "No API key found. Add GEMINI_API_KEY to .env "
            "or enter one below.",
            icon="🔑",
        )

    st.text_input(
        "Gemini API key (this session only, not saved)",
        type="password",
        key="sidebar_key",
    )

    model = st.text_input(
        "Gemini model",
        value=env_settings.model,
        help="Gemini model to use. Default from GEMINI_MODEL.",
    )

    st.caption(
        "StudyMate sends your notes to the Google Gemini API. "
        "Do not upload confidential or personal information."
    )


def current_settings() -> GenerationSettings:
    """Build generation settings using the selected model."""
    s = GenerationSettings.from_env()
    s.model = model.strip() or s.model
    return s


# ------------------------------------------------------------------ helpers --

def load_sample(
    name_key: str,
    target: str,
    subject_target: str,
) -> None:
    name = st.session_state.get(name_key)

    if name and name in SAMPLE_FILES:
        st.session_state[target] = (
            SAMPLES_DIR / SAMPLE_FILES[name]
        ).read_text(encoding="utf-8")

        st.session_state[subject_target] = name.split(" (")[0]


def version_label(v: str) -> str:
    try:
        return load_version(v).label
    except Exception:
        return v.upper()


def run_generation(
    notes: str,
    subject: str,
    version: str,
    detail: str,
) -> StudyPackResult:

    client = make_client(active_api_key())

    return generate_study_pack(
        notes,
        subject,
        version,
        detail,
        client=client,
        settings=current_settings(),
    )


def render_markdown_block(
    md: str,
    empty: str = "Not generated.",
) -> None:

    if md and md.strip():
        st.markdown(md)
    else:
        st.markdown(
            f"<span class='sm-muted'>{empty}</span>",
            unsafe_allow_html=True,
        )


def show_validation(v) -> None:
    for e in v.errors:
        st.error(e)

    for w in v.warnings:
        st.warning(w)


def disclaimer() -> None:
    st.markdown(
        """
        <div class='sm-note'>
        Generated by Google Gemini, an external AI model.
        It can contain mistakes or omissions. Always check answers
        against your original lecture notes.
        </div>
        """,
        unsafe_allow_html=True,
    )


# ------------------------------------------------------------------- header --

top_l, top_r = st.columns(
    [1, 1.3],
    vertical_alignment="center",
)

with top_l:
    st.markdown(
        "<div class='sm-brand'>"
        "<div class='sm-logo'>S</div>"
        "<div class='sm-word'>StudyMate</div>"
        "</div>",
        unsafe_allow_html=True,
    )

with top_r:
    pages = ["Generate", "Compare prompts", "About"]

    page = (
        st.segmented_control(
            "Navigation",
            pages,
            default="Generate",
            label_visibility="collapsed",
            key="nav",
        )
        or "Generate"
    )

versions = list_versions()


# =============================================================== GENERATE ====

def page_generate() -> None:

    st.markdown(
        """
        <div class='sm-hero'>
        <h1>Turn your lecture notes into smarter revision.</h1>
        <p>
        Paste your notes and get a summary, key concepts, five practice
        questions and a revision checklist that stay grounded in what you wrote.
        </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    left, right = st.columns(
        [1.75, 1],
        gap="large",
    )

    with left:
        with st.container(border=True):

            st.markdown(
                "<div class='sm-label'>Your notes</div>",
                unsafe_allow_html=True,
            )

            st.text_input(
                "Subject or topic",
                key="subject_input",
                placeholder="e.g. Data Structures — Binary Search",
            )

            st.text_area(
                "Lecture notes",
                key="notes_input",
                height=300,
                placeholder="Paste your lecture notes here…",
            )

            uploaded = st.file_uploader(
                "…or upload a .txt file",
                type=["txt"],
            )

            st.selectbox(
                "Try a sample",
                ["—", *SAMPLE_FILES],
                key="gen_sample",
                on_change=load_sample,
                args=(
                    "gen_sample",
                    "notes_input",
                    "subject_input",
                ),
            )

    with right:
        with st.container(border=True):

            st.markdown(
                "<div class='sm-label'>Options</div>",
                unsafe_allow_html=True,
            )

            default_v = (
                "v3" if "v3" in versions else versions[-1]
            )

            version = st.selectbox(
                "Prompt version",
                versions,
                index=versions.index(default_v),
                format_func=version_label,
            )

            try:
                with st.expander("What this version changes"):
                    st.caption(
                        load_version(version).description
                    )
            except Exception as exc:
                st.error(str(exc))

            detail = (
                st.segmented_control(
                    "Detail level",
                    list(DETAIL_LEVELS),
                    default=DEFAULT_DETAIL,
                )
                or DEFAULT_DETAIL
            )

            if version == "v1":
                st.caption(
                    "V1 is the baseline and ignores the detail level."
                )

            go = st.button(
                "Generate Study Pack",
                type="primary",
                width="stretch",
            )

    if go:

        source = st.session_state.notes_input

        if uploaded is not None:
            up = decode_upload(
                uploaded.getvalue(),
                uploaded.name,
            )

            if not up.ok:
                show_validation(up)
                return

            source = up.text
            st.info(f"Using uploaded file: {uploaded.name}")

        v = validate_notes(source)

        subject, sw = validate_subject(
            st.session_state.subject_input
        )

        v.warnings.extend(sw)
        show_validation(v)

        if not v.ok:
            return

        if not active_api_key():
            st.error(
                "No Gemini API key found. Add GEMINI_API_KEY "
                "to your .env file or paste a key in the sidebar "
                "(open it with the arrow, top left)."
            )
            return

        with st.spinner(
            "Running the three prompt tasks "
            "(summary, questions, revision)…"
        ):
            try:
                st.session_state.result = run_generation(
                    v.text,
                    subject,
                    version,
                    detail,
                )

                st.session_state.result_notes = v.text

            except Exception as exc:
                st.error(str(exc))
                return

    res: StudyPackResult | None = st.session_state.result

    if res is not None:
        render_result(
            res,
            st.session_state.result_notes,
        )


# ------------------------------------------------------------ render result --

def render_result(
    res: StudyPackResult,
    notes: str,
) -> None:

    errors = res.errors

    if errors and all(
        not t.ok for t in res.tasks.values()
    ):
        msgs = {
            t.error
            for t in res.tasks.values()
            if t.error
        }

        for m in msgs:
            st.error(m)

        return

    pack = build_study_pack(
        {
            k: t.text
            for k, t in res.tasks.items()
            if t.ok
        }
    )

    metrics = evaluate_pack(
        pack,
        notes,
        res.detail_level,
    )

    tokens = sum(
        (t.input_tokens or 0) + (t.output_tokens or 0)
        for t in res.tasks.values()
    )

    st.markdown(
        "<div style='height:1.2rem'></div>",
        unsafe_allow_html=True,
    )

    with st.container(border=True):

        h_l, h_r = st.columns(
            [3, 1.2],
            vertical_alignment="center",
        )

        with h_l:
            st.markdown(
                f"<span class='sm-badge dark'>"
                f"{res.version.upper()}</span>"
                f"<span class='sm-badge'>"
                f"{res.detail_level}</span>"
                f"<span class='sm-badge'>"
                f"{html.escape(res.model)}</span>",
                unsafe_allow_html=True,
            )

            st.markdown(
                f"### Study pack"
                f"{': ' + html.escape(res.subject) if res.subject else ''}"
            )

        with h_r:

            md = to_markdown(
                pack,
                res.subject,
                res.version,
                res.model,
            )

            fname = (
                (res.subject or "study_pack")
                .lower()
                .replace(" ", "_")[:40]
            )

            st.download_button(
                "Download .md",
                md,
                file_name=f"{fname}.md",
                mime="text/markdown",
                width="stretch",
            )

            st.download_button(
                "Download .txt",
                md,
                file_name=f"{fname}.txt",
                mime="text/plain",
                width="stretch",
            )

        st.markdown(
            "<div class='sm-meta'>"
            f"<div>Time<b>{res.total_latency_s:.1f}s</b></div>"
            f"<div>Tokens<b>{tokens:,}</b></div>"
            f"<div>Questions<b>{metrics['question_count']}</b></div>"
            f"<div>Summary words<b>{metrics['summary_words']}</b></div>"
            "</div>",
            unsafe_allow_html=True,
        )

        for e in errors:
            st.warning(
                f"Part of the pack failed — {e}"
            )

        for task, reason in pack.insufficient.items():
            st.warning(
                f"The model reported the notes are insufficient for "
                f"{TASK_LABELS[task]}: {reason}"
            )

        disclaimer()

        tabs = st.tabs(
            [
                "Summary",
                "Key Concepts",
                "Practice Questions",
                "Revision Points",
                "Verification",
                "Copy",
            ]
        )

        with tabs[0]:

            if pack.main_topic:
                st.markdown(
                    "<div class='sm-label'>Main topic</div>",
                    unsafe_allow_html=True,
                )

                st.markdown(pack.main_topic)

            st.markdown(
                "<div class='sm-label'>Summary</div>",
                unsafe_allow_html=True,
            )

            render_markdown_block(pack.summary)

        with tabs[1]:

            render_markdown_block(
                pack.key_concepts,
                "This prompt version did not produce a separate "
                "Key Concepts section (see the Summary tab).",
            )

        with tabs[2]:
            render_questions(pack)

        with tabs[3]:

            render_markdown_block(pack.revision_points)

            if pack.definitions:
                st.markdown("#### Key definitions")
                st.markdown(pack.definitions)

            if pack.checklist:
                st.markdown("#### Quick revision checklist")
                st.markdown(pack.checklist)

        with tabs[4]:
            render_verification(
                pack,
                notes,
                metrics,
            )

        with tabs[5]:
            st.caption(
                "Use the copy icon in the top-right corner of the box."
            )

            st.code(
                md,
                language="markdown",
                wrap_lines=True,
            )


# ---------------------------------------------------------- render questions --

def render_questions(pack: StudyPack) -> None:

    if not pack.questions:

        st.caption(
            "This prompt version returned unstructured questions; "
            "shown as received."
        )

        render_markdown_block(pack.questions_raw)
        return

    for q in pack.questions:

        with st.container(border=True):

            badge = (
                f"<span class='sm-badge'>{q.qtype}</span>"
                if q.qtype
                else ""
            )

            st.markdown(
                f"<span class='sm-badge dark'>Q{q.number}</span>"
                f"{badge}"
                f"<div class='sm-q'>{html.escape(q.text)}</div>",
                unsafe_allow_html=True,
            )

            if q.placeholder:
                continue

            with st.expander("Show answer"):

                st.markdown(
                    q.answer or "_No answer parsed._"
                )

                if q.evidence:
                    st.caption(
                        f'Evidence from notes: "{q.evidence}"'
                    )


# -------------------------------------------------------- render verification --

def render_verification(
    pack: StudyPack,
    notes: str,
    metrics: dict,
) -> None:

    st.markdown(
        "This tab checks how closely the output is tied to your notes. "
        "A match shows the claim is anchored in your notes. "
        "**It does not prove the content is correct.**"
    )

    ev = verify_evidence(pack, notes)

    c1, c2, c3 = st.columns(3)

    c1.metric(
        "Evidence quotes",
        metrics["evidence_quotes"],
    )

    rate = metrics["evidence_match_rate"]

    c2.metric(
        "Quotes found in notes",
        f"{rate:.0%}" if rate is not None else "—",
    )

    ntr = metrics["novel_term_ratio"]

    c3.metric(
        "Terms not in notes",
        f"{ntr:.0%}" if ntr is not None else "—",
        help=(
            "Share of distinct content words in the output that "
            "never appear in the notes. Synonyms also count, "
            "so treat this as a rough signal."
        ),
    )

    if ev:

        df = pd.DataFrame(ev)

        df["Found in notes"] = df[
            "Found in notes"
        ].map(
            {
                True: "✓ Found",
                False: "✗ Not found",
            }
        )

        st.dataframe(
            df,
            width="stretch",
            hide_index=True,
        )

    else:
        st.caption(
            "This prompt version does not ask for evidence quotes (V3 does)."
        )

    if pack.coverage:
        st.markdown(
            "#### Source coverage (reported by the model)"
        )

        st.markdown(pack.coverage)

    terms = novel_terms(
        "\n".join(pack.raw.values()),
        notes,
    )

    if terms:

        st.markdown(
            "#### Words in the output that are not in your notes"
        )

        st.caption(
            "Worth a quick look. Most are harmless rewording; "
            "any new facts should be checked."
        )

        st.write(", ".join(terms))


# ================================================================ COMPARE ====

def page_compare() -> None:

    st.markdown(
        """
        <div class='sm-hero'>
        <h1>Compare prompt versions</h1>
        <p>
        Run the same notes through V1, V2 and V3 and compare
        structure, length and grounding side by side.
        </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    with st.container(border=True):

        c1, c2 = st.columns(
            [1.75, 1],
            gap="large",
        )

        with c1:

            st.selectbox(
                "Load sample notes",
                ["—", *SAMPLE_FILES],
                key="cmp_sample",
                on_change=load_sample,
                args=(
                    "cmp_sample",
                    "cmp_notes",
                    "cmp_subject",
                ),
            )

            st.text_area(
                "Lecture notes",
                key="cmp_notes",
                height=240,
                placeholder="Paste the notes to test…",
            )

        with c2:

            subject = st.text_input(
                "Subject",
                key="cmp_subject",
            )

            chosen = st.multiselect(
                "Versions",
                versions,
                default=versions,
                format_func=lambda v: v.upper(),
            )

            detail = (
                st.segmented_control(
                    "Detail level",
                    list(DETAIL_LEVELS),
                    default=DEFAULT_DETAIL,
                    key="cmp_detail",
                )
                or DEFAULT_DETAIL
            )

            st.caption(
                f"Uses {3 * len(chosen)} API calls."
            )

            go = st.button(
                "Run comparison",
                type="primary",
                width="stretch",
                disabled=not chosen,
            )

    if go:

        v = validate_notes(
            st.session_state.get("cmp_notes", "")
        )

        show_validation(v)

        if not v.ok:
            return

        if not active_api_key():
            st.error(
                "No Gemini API key found. Add GEMINI_API_KEY "
                "to .env or use the sidebar."
            )
            return

        with st.spinner(
            f"Generating with {', '.join(x.upper() for x in chosen)}…"
        ):

            try:

                with ThreadPoolExecutor(
                    max_workers=len(chosen)
                ) as pool:

                    results = list(
                        pool.map(
                            lambda ver: run_generation(
                                v.text,
                                subject,
                                ver,
                                detail,
                            ),
                            chosen,
                        )
                    )

            except Exception as exc:
                st.error(str(exc))
                return

        st.session_state.compare = results
        st.session_state.compare_notes = v.text

    results: list[StudyPackResult] | None = (
        st.session_state.compare
    )

    if not results:
        return

    notes = st.session_state.compare_notes

    rows, packs = {}, {}

    for r in results:

        pack = build_study_pack(
            {
                k: t.text
                for k, t in r.tasks.items()
                if t.ok
            }
        )

        packs[r.version] = pack

        m = evaluate_pack(
            pack,
            notes,
            r.detail_level,
        )

        m["latency_s"] = r.total_latency_s

        m["tokens"] = sum(
            (t.input_tokens or 0) + (t.output_tokens or 0)
            for t in r.tasks.values()
        )

        m["errors"] = (
            "; ".join(r.errors) or "none"
        )

        rows[r.version.upper()] = m

    df = pd.DataFrame(rows)

    st.markdown("### Automatic metrics")

    st.caption(
        "Computed locally from these outputs. They are proxies — "
        "read the outputs below before drawing conclusions."
    )

    st.dataframe(
        df.astype(str),
        width="stretch",
    )

    st.download_button(
        "Download metrics (.csv)",
        df.to_csv().encode(),
        "comparison_metrics.csv",
        mime="text/csv",
    )

    st.markdown("### Outputs side by side")

    task = (
        st.segmented_control(
            "Task",
            list(TASKS),
            default="SUMMARY",
            format_func=lambda t: TASK_LABELS[t],
            key="cmp_task",
        )
        or "SUMMARY"
    )

    cols = st.columns(len(results))

    for col, r in zip(cols, results):

        with col:

            with st.container(border=True):

                st.markdown(
                    f"<span class='sm-badge dark'>"
                    f"{r.version.upper()}</span>",
                    unsafe_allow_html=True,
                )

                t = r.tasks[task]

                if t.error:
                    st.error(t.error)
                else:
                    st.markdown(t.text)


# ================================================================== ABOUT ====

def page_about() -> None:

    st.markdown(
        """
        <div class='sm-hero'>
        <h1>How StudyMate works</h1>
        <p>
        A Prompt Engineering project by team Promptly Unemployed,
        Bennett University.
        </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    a, b, c = st.columns(3)

    for col, task, desc in [
        (
            a,
            "SUMMARY",
            "Main topic, a length-controlled summary and key concepts.",
        ),
        (
            b,
            "QUESTIONS",
            "Exactly five practice questions, factual and conceptual, with answers.",
        ),
        (
            c,
            "REVISION",
            "Revision points, definitions from the notes and a quick checklist.",
        ),
    ]:

        with col:

            with st.container(border=True):

                st.markdown(
                    f"**{TASK_LABELS[task]}**"
                )

                st.caption(desc)

    st.markdown(
        "Each task is a separate prompt sent to the model in parallel. "
        "The outputs are parsed into sections, checked locally "
        "(structure, length, evidence quotes) and shown in tabs."
    )

    st.markdown("### Prompt versions")

    for v in versions:

        pv = load_version(v)

        with st.expander(pv.label):

            st.caption(pv.description)

            st.code(
                pv.path.read_text(encoding="utf-8"),
                language="text",
                wrap_lines=True,
            )

    st.markdown("### Responsible AI")

    st.markdown(
        """
        - Notes are sent to an external AI model (**Google Gemini**).
          Don't upload confidential or personally identifiable material;
          StudyMate warns if it sees emails or phone numbers.
        - Generated content **can be wrong**. Use it to support your revision,
          not replace your notes.
        - Prompt V3 tells the model to use only your notes, say when
          information is missing, and ignore instructions hidden inside the notes.
        - The Verification tab checks evidence quotes against your notes.
          A match shows the claim is anchored in the notes, **not** that it is correct.
        - The Gemini API key stays on your machine (.env), in Streamlit
          Secrets, or in this browser session only.
        """
    )

    st.markdown("### Limitations")

    st.markdown(
        """
        - Plain text input only (.txt or pasted); no PDF/slides yet.
        - Notes are limited to 40,000 characters per request.
        - Automatic metrics are proxies; quality judgements need a human reviewer.
        - Output varies between runs, so results can differ slightly each time.
        """
    )


# =============================================================== APP ROUTER ==

if page == "Generate":
    page_generate()

elif page == "Compare prompts":
    page_compare()

else:
    page_about()

