"""Offline HTML report; embedded records are escaped and rendered as text."""

import json
from pathlib import Path

from .session import pair_transactions, summarize


def render_report(records, path):
    data = json.dumps({"records": records, "summary": summarize(records),
                       "transactions": pair_transactions(records)}, allow_nan=False)
    # Prevent data from terminating the script tag, even when labels contain HTML.
    data = data.replace("<", "\\u003c").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
    template = Path(__file__).with_name("report.html").read_text(encoding="utf-8")
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(template.replace("/*SESSION_DATA*/null", data), encoding="utf-8")
    return target
