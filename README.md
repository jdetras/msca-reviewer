# 🎓 MSCA Reviewer Panel

A panel of AI **reviewer agents** that scrutinise a **Marie Skłodowska-Curie Actions
(MSCA) Postdoctoral Fellowship** proposal the way a real evaluation panel would —
scoring it against the official **Excellence (50%) / Impact (30%) / Implementation (20%)**
criteria, producing a **weighted percentage grade**, and returning a prioritised list of
**what is missing and what to improve**.

Part of [ClawBioCrop](https://github.com/jdetras/clawbiocrop). Self-contained: the panel,
the **Word/PDF parser** and the **web UI** all run on the pure Python standard library — no
third-party packages required (PDF reading is the one optional extra, see below).

## The panel

| Agent | Role | Weight |
|---|---|---|
| **Reviewer 1 — Excellence** | Objectives & state of the art, methodology (gender dimension, open science), training & 2-way knowledge transfer, supervision | 50% |
| **Reviewer 2 — Impact** | Career/employability, dissemination/exploitation/communication, magnitude of impact | 30% |
| **Reviewer 3 — Implementation** | Work plan, work packages, Gantt, risks, host capacity | 20% |
| **Reviewer 4 — Compliance** | Page limit, formatting, ethics/open-science/gender presence | admissibility gate |
| **Panel Chair** | Aggregates → weighted % grade + verdict (70% threshold, ~90% competitive) | — |
| **Feedback agent** | Gap analysis + ranked improvement plan | — |

## Quick start

```bash
# Score a proposal draft — accepts .md, .txt, .docx or .pdf
python msca_reviewer.py --input proposal.docx --output report_dir

# No file yet? Run the built-in synthetic demo
python msca_reviewer.py --demo --output /tmp/msca_demo
```

Outputs `report.md` (human-readable scorecards + feedback) and `result.json`
(machine-readable scores, weighted breakdown and improvement plan).

## Web UI

Prefer a browser? Launch the built-in local web app, open the link, drop in a
proposal file and read the graded report on the page:

```bash
python app.py            # → http://127.0.0.1:8000
python app.py --port 9000
```

The server is standard-library only and runs **entirely on your machine** — proposals
are processed locally and never uploaded anywhere.

## Supported proposal formats

| Format | Support |
|---|---|
| `.md`, `.markdown`, `.txt` | ✅ built-in |
| `.docx` (Word) | ✅ built-in (parsed via stdlib `zipfile` — no Word/`python-docx` needed) |
| `.pdf` | ✅ with an optional engine: `pip install pypdf` (or `pdfminer.six`) |
| `.doc` (legacy binary) | ❌ — re-save as `.docx` or PDF first |

```
$ python msca_reviewer.py --demo --output /tmp/msca_demo
MSCA panel grade: 92.6%  (Competitive / fundable)
  Threshold 70% met; report → /tmp/msca_demo/report.md
```

## How it scores

1. Each reviewer scores its sub-criteria 0–5 from the rubric in
   [`rules/msca_rules.json`](rules/msca_rules.json) (evidence detection with a saturation
   point, so a convincingly-addressed element earns full marks).
2. Criterion score = mean of sub-scores; **weighted % = Σ(score/5 × weight × 100)**.
3. Verdict against the **70% funding threshold** and **~90% competitiveness** target.
4. Feedback ranks fixes by the weighted points each can recover.

## Rules base

`rules/msca_rules.json` encodes the official criteria, sub-criteria wording, weights,
thresholds, Part B formatting limits (10 pages, Times New Roman 11pt, ≥15 mm margins) and a
set of curated evaluator tips with sources. Update it each call cycle.

## Tests

```bash
pip install pytest      # plus optional 'pypdf' to exercise the PDF path
pytest tests/
```

## Disclaimer

MSCA-Reviewer is a research/educational tool. It is **not** the European Commission, REA, or
an evaluation panel, and its scores are **heuristic estimates only** — not official results.
Always verify against the current MSCA Work Programme, Guide for Applicants and call-specific
evaluation form before submitting. Keep unpublished proposals confidential — they are
processed locally and never uploaded.

## Sources

- [MSCA Postdoctoral Fellowships — REA (how to apply)](https://rea.ec.europa.eu/funding-and-grants/horizon-europe-marie-sklodowska-curie-actions/horizon-europe-msca-how-apply_en)
- [MSCA Postdoctoral Fellowships — European Commission](https://marie-sklodowska-curie-actions.ec.europa.eu/actions/postdoctoral-fellowships)
- [Ten simple rules for a successful MSCA application (PLOS Comput Biol)](https://pmc.ncbi.nlm.nih.gov/articles/PMC9387847/)
