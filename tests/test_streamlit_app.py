"""Red/green TDD suite for the Streamlit app + its pure display helpers.

The display helpers run everywhere; the full AppTest runs only where Streamlit
is installed (skipped otherwise, like the optional PDF backend).

Run: pytest tests/test_streamlit_app.py
"""
import sys
from pathlib import Path

import pytest

SKILL_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL_DIR))

from reviewers import load_rules  # noqa: E402
from reviewers.summary import grade_headline, summary_table, priority_lines  # noqa: E402
from msca_reviewer import run_panel  # noqa: E402


@pytest.fixture(scope="module")
def demo_result():
    rules = load_rules()
    text = (SKILL_DIR / "examples" / "demo_proposal.md").read_text(encoding="utf-8")
    return run_panel(text, rules)


def test_grade_headline_shape(demo_result):
    h = grade_headline(demo_result)
    assert 0 <= h["percentage"] <= 100
    assert isinstance(h["threshold_met"], bool)
    assert isinstance(h["competitive"], bool)
    assert h["label"]


def test_summary_table_has_three_criteria_plus_total(demo_result):
    rows = summary_table(demo_result)
    names = [r["Criterion"] for r in rows]
    assert any("Excellence" in n for n in names)
    assert any("Impact" in n for n in names)
    assert any("Implementation" in n for n in names)
    assert names[-1] == "Total"
    # the total weighted points should equal the headline percentage
    assert rows[-1]["Weighted pts"] == round(demo_result["percentage"], 1)


def test_priority_lines_are_strings(demo_result):
    lines = priority_lines(demo_result, limit=3)
    assert len(lines) <= 3
    assert all(isinstance(x, str) and x for x in lines)


def test_streamlit_app_runs_demo():
    """Full smoke test via Streamlit's AppTest (skipped if streamlit absent)."""
    at_mod = pytest.importorskip("streamlit.testing.v1")
    AppTest = at_mod.AppTest
    at = AppTest.from_file(str(SKILL_DIR / "streamlit_app.py"), default_timeout=30)
    at.run()
    assert not at.exception
    # Click the demo button and confirm a grade metric is rendered.
    demo_btns = [b for b in at.button if "demo" in b.label.lower()]
    assert demo_btns, "demo button should be present"
    demo_btns[0].click().run()
    assert not at.exception
    metric_values = [m.value for m in at.metric]
    assert any("%" in str(v) for v in metric_values)
