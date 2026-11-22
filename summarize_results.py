"""Summarise tests/evaluation_results.csv into report-ready tables and a chart.

    python summarize_results.py

Writes
  docs/evaluation_summary.md            result matrix + per-version metric averages
  docs/diagrams/metrics_by_version.png  bar chart (only if API results exist)

Only rows that were actually executed are used. Nothing is estimated or filled in.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent
CSV = ROOT / "tests" / "evaluation_results.csv"
OUT_MD = ROOT / "docs" / "evaluation_summary.md"
OUT_PNG = ROOT / "docs" / "diagrams" / "metrics_by_version.png"

NUMERIC = ["question_count", "summary_words", "evidence_match_rate", "novel_term_ratio",
           "duplicate_bullets", "latency_s", "input_tokens", "output_tokens"]
RUBRIC = ["rubric_relevance", "rubric_accuracy", "rubric_completeness", "rubric_clarity",
          "rubric_consistency", "rubric_unsupported_info"]


def main() -> None:
    df = pd.read_csv(CSV, dtype=str, keep_default_na=False)
    lines = ["# Evaluation Summary", "",
             f"_Generated from `tests/evaluation_results.csv` ({len(df)} rows). "
             "Only executed rows are counted._", ""]

    matrix = df.pivot_table(index=["test_id", "title"], columns="prompt_version",
                            values="result", aggfunc="first", fill_value="")
    lines += ["## Result matrix", "", matrix.reset_index().to_markdown(index=False), ""]

    counts = df.groupby(["prompt_version", "result"]).size().unstack(fill_value=0)
    lines += ["## Result counts by prompt version", "", counts.to_markdown(), ""]

    api = df[~df["prompt_version"].str.startswith("n/a") & ~df["result"].isin(["NOT RUN", ""])].copy()
    if api.empty:
        lines += ["## Metrics", "",
                  "No API-based results yet. Run `python run_evaluation.py` with an "
                  "OPENAI_API_KEY set, then run this script again.", ""]
        OUT_MD.write_text("\n".join(lines), encoding="utf-8")
        print(f"Wrote {OUT_MD.relative_to(ROOT)} (no API results yet)")
        return

    for c in NUMERIC + RUBRIC:
        api[c] = pd.to_numeric(api[c], errors="coerce")
    means = api.groupby("prompt_version")[NUMERIC].mean().round(3)
    lines += ["## Mean automatic metrics by prompt version", "",
              "Means over the executed API test cases. `evidence_match_rate` only exists "
              "where evidence quotes were produced.", "", means.to_markdown(), ""]

    if api[RUBRIC].notna().any().any():
        rub = api.groupby("prompt_version")[RUBRIC].mean().round(2)
        n = api.groupby("prompt_version")[RUBRIC[0]].count()
        lines += ["## Mean human rubric scores (1–5)", "",
                  f"Rows scored per version: {n.to_dict()}", "", rub.to_markdown(), ""]
    else:
        lines += ["## Human rubric scores", "", "Not scored yet — fill the rubric_* columns "
                  "in the CSV after reading the outputs (see docs/testing_methodology.md).", ""]

    OUT_MD.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {OUT_MD.relative_to(ROOT)}")

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    pass_rate = (api.assign(p=api["result"].eq("PASS"))
                 .groupby("prompt_version")["p"].mean())
    fig, axes = plt.subplots(1, 3, figsize=(11, 3.2))
    panels = [(pass_rate, "Automatic pass rate", True),
              (means["novel_term_ratio"], "Mean share of terms not in notes", True),
              (means["summary_words"], "Mean summary words", False)]
    for ax, (series, title, pct) in zip(axes, panels):
        series = series.dropna()
        ax.bar([v.upper() for v in series.index], series.values, color="#2a2a2a", width=0.55)
        ax.set_title(title, fontsize=10)
        if pct:
            ax.set_ylim(0, 1)
            ax.yaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0))
        for s in ("top", "right"):
            ax.spines[s].set_visible(False)
        ax.tick_params(labelsize=9)
    fig.tight_layout()
    fig.savefig(OUT_PNG, dpi=200)
    print(f"Wrote {OUT_PNG.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
