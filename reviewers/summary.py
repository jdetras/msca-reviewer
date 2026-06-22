"""Display-ready summaries of a panel result, independent of any UI framework.

Keeping this logic out of the Streamlit/Flask layers makes it unit-testable
without a running server or browser.
"""
from __future__ import annotations

from typing import Dict, List


def grade_headline(result: Dict) -> Dict:
    """The top-line numbers a UI shows first."""
    return {
        "percentage": round(result["percentage"], 1),
        "label": result["label"],
        "note": result["note"],
        "threshold_pct": result["threshold_pct"],
        "threshold_met": bool(result["threshold_met"]),
        "competitive_target_pct": result["competitive_target_pct"],
        "competitive": bool(result["competitive"]),
        "word_count": result.get("word_count"),
    }


def summary_table(result: Dict) -> List[Dict]:
    """Weighted-breakdown rows, ready to drop into a table widget."""
    rows = []
    for b in result["breakdown"]:
        rows.append({
            "Criterion": b["criterion_name"],
            "Weight": f"{b['weight_pct']:.0f}%",
            "Score /5": round(b["score"], 2),
            "Weighted pts": round(b["weighted_points"], 1),
        })
    rows.append({
        "Criterion": "Total",
        "Weight": "",
        "Score /5": "",
        "Weighted pts": round(result["percentage"], 1),
    })
    return rows


def priority_lines(result: Dict, limit: int = 5) -> List[str]:
    """Top improvement priorities as plain strings."""
    out = []
    for p in result["feedback"]["top_priorities"][:limit]:
        imp = f" (≈+{p['weighted_impact']:.1f} pts)" if p.get("weighted_impact") else ""
        out.append(f"{p['criterion']} → {p['subcriterion']}{imp}: {p['action']}")
    return out
