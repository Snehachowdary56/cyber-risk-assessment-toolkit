"""Run the whole process on a requests file and write every output to one folder."""
from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from .assessment import assess, load_controls
from .intake import IntakeTracker
from .reports import (
    REGISTER_COLUMNS,
    assessment_report,
    dashboard_html,
    intake_rows,
    register_rows,
    risk_briefing,
    summary,
    write_csv,
    write_register_xlsx,
)
from .triage import assign_level

ROOT = Path(__file__).resolve().parent.parent


def run(requests_csv: Path, answers_json: Path, controls_json: Path, out: Path, as_of: date) -> dict:
    tracker = IntakeTracker(year=as_of.year)
    tracker.load_csv(str(requests_csv))
    controls = load_controls(str(controls_json))
    answers = json.loads(answers_json.read_text(encoding="utf-8"))

    assessments = []
    for req in tracker.requests:
        req.level, req.level_reasons = assign_level(req)
        assessments.append(assess(req, controls, answers.get(req.system_name, {})))

    (out / "reports").mkdir(parents=True, exist_ok=True)
    (out / "briefings").mkdir(parents=True, exist_ok=True)
    intake = intake_rows(assessments, as_of)
    register = register_rows(assessments)
    write_csv(out / "intake_log.csv", intake)
    write_csv(out / "risk_register.csv", register, REGISTER_COLUMNS)
    write_csv(out / "rejected_requests.csv",
              [{"Row": r.row_number, "Reason": r.reason, "System": r.raw.get("system_name", "")} for r in tracker.rejected],
              ["Row", "Reason", "System"])
    write_register_xlsx(out / "risk_register.xlsx", register, intake)
    for a in assessments:
        (out / "reports" / f"{a.request.request_id}.md").write_text(assessment_report(a), encoding="utf-8")
        (out / "briefings" / f"{a.request.request_id}_briefing.md").write_text(risk_briefing(a), encoding="utf-8")
    s = summary(assessments, tracker, as_of)
    (out / "summary.json").write_text(json.dumps(s, indent=2), encoding="utf-8")
    (out / "dashboard.html").write_text(dashboard_html(s, intake, register), encoding="utf-8")
    return s


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Cyber risk assessment toolkit")
    p.add_argument("--requests", type=Path, default=ROOT / "data" / "sample_requests.csv")
    p.add_argument("--answers", type=Path, default=ROOT / "data" / "sample_answers.json")
    p.add_argument("--controls", type=Path, default=ROOT / "data" / "controls.json")
    p.add_argument("--out", type=Path, default=ROOT / "output")
    p.add_argument("--as-of", type=date.fromisoformat, default=date(2026, 11, 19))
    args = p.parse_args(argv)
    s = run(args.requests, args.answers, args.controls, args.out, args.as_of)
    print(json.dumps(s, indent=2))
    return 0
