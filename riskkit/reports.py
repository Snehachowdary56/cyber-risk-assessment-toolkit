"""Outputs: intake log, risk register (CSV and Excel), risk assessment reports, risk briefings and a dashboard."""
from __future__ import annotations

import csv
import html
from collections import Counter
from datetime import date
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter

from .assessment import FUNCTIONS, Assessment
from .intake import IntakeTracker
from .triage import SLA_BUSINESS_DAYS, business_days_between, due_date

RATING_COLOURS = {"Critical": "C00000", "High": "FF6600", "Medium": "FFC000", "Low": "70AD47"}
REGISTER_COLUMNS = ["Risk ID", "Request ID", "System", "Department", "Owner", "NIST CSF function",
                    "NIST CSF category", "Control", "Answer", "Risk", "Likelihood", "Impact", "Score",
                    "Rating", "Recommended treatment", "Status"]


def status_of(a: Assessment) -> str:
    return "Closed" if a.request.completed else "In assessment"


def intake_rows(assessments: list[Assessment], as_of: date) -> list[dict]:
    rows = []
    for a in assessments:
        r = a.request
        due = due_date(r)
        end = r.completed or as_of
        days = business_days_between(r.received, end)
        rows.append({
            "Request ID": r.request_id, "Received": r.received.isoformat(), "Requestor": r.requestor,
            "Department": r.department, "System": r.system_name, "Level": r.level,
            "Level reasons": "; ".join(r.level_reasons), "Status": status_of(a),
            "Due": due.isoformat(), "Completed": r.completed.isoformat() if r.completed else "",
            "Business days": days,
            "On time": ("yes" if r.completed <= due else "no") if r.completed else ("overdue" if as_of > due else "open"),
            "Findings": len(a.findings), "Overall rating": a.overall_rating,
            "Compliance %": round(100 * a.compliance),
        })
    return rows


def register_rows(assessments: list[Assessment]) -> list[dict]:
    rows = []
    for a in assessments:
        for f in a.findings:
            c = f.control
            rows.append({
                "Risk ID": f.risk_id, "Request ID": a.request.request_id, "System": a.request.system_name,
                "Department": a.request.department, "Owner": a.request.requestor,
                "NIST CSF function": c["function"], "NIST CSF category": c["csf"], "Control": c["id"],
                "Answer": f.answer, "Risk": c["risk"], "Likelihood": f.likelihood, "Impact": f.impact,
                "Score": f.score, "Rating": f.rating, "Recommended treatment": c["fix"],
                "Status": "Open" if not a.request.completed else "Treatment agreed",
            })
    rows.sort(key=lambda r: (-r["Score"], r["Risk ID"]))
    return rows


def write_csv(path: Path, rows: list[dict], columns: list[str] | None = None) -> None:
    columns = columns or (list(rows[0]) if rows else [])
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=columns)
        w.writeheader()
        w.writerows(rows)


def write_register_xlsx(path: Path, register: list[dict], intake: list[dict]) -> None:
    wb = Workbook()
    for title, rows, cols in [("Risk Register", register, REGISTER_COLUMNS),
                              ("Intake Log", intake, list(intake[0]) if intake else [])]:
        ws = wb.active if title == "Risk Register" else wb.create_sheet(title)
        ws.title = title
        ws.append(cols)
        for cell in ws[1]:
            cell.font = Font(bold=True, color="FFFFFF")
            cell.fill = PatternFill("solid", fgColor="1F3A68")
        for r in rows:
            ws.append([r[c] for c in cols])
        for col_idx, col in enumerate(cols, start=1):
            width = max([len(str(col))] + [len(str(r[col])) for r in rows]) + 2
            ws.column_dimensions[get_column_letter(col_idx)].width = min(width, 60)
        ws.freeze_panes = "A2"
        ws.auto_filter.ref = ws.dimensions
        rating_col = next((i for i, c in enumerate(cols, start=1) if c in ("Rating", "Overall rating")), None)
        if rating_col:
            for row in ws.iter_rows(min_row=2, min_col=rating_col, max_col=rating_col):
                for cell in row:
                    colour = RATING_COLOURS.get(cell.value)
                    if colour:
                        cell.fill = PatternFill("solid", fgColor=colour)
                        cell.font = Font(bold=True, color="FFFFFF")
    wb.save(path)


def assessment_report(a: Assessment) -> str:
    r = a.request
    lines = [
        f"# Cyber Risk Assessment Report: {r.system_name}",
        "",
        f"**Request:** {r.request_id} | **Requestor:** {r.requestor} ({r.department}) | **Received:** {r.received}",
        f"**Assessment level:** {r.level} ({'; '.join(r.level_reasons)})",
        f"**Overall risk rating:** {a.overall_rating} | **Questions met:** {round(100 * a.compliance)}% of {len(a.asked)}",
        "",
        "## Scope",
        "",
        f"{r.description}. Data classification: {r.data_classification}. Vendor: {'yes' if r.vendor else 'no'}. "
        f"Internet-facing: {'yes' if r.internet_facing else 'no'}. Operational technology: {'yes' if r.operational_technology else 'no'}. "
        f"Users: {r.users}.",
        "",
        "## Results by NIST Cybersecurity Framework function",
        "",
        "| Function | Questions met |",
        "|---|---|",
    ]
    for fn, share in a.compliance_by_function().items():
        lines.append(f"| {fn} | {'not assessed at this level' if share is None else f'{round(100 * share)}%'} |")
    lines += ["", "## Findings", ""]
    if not a.findings:
        lines.append("No gaps found at this assessment level.")
    else:
        lines += ["| Risk ID | Control | Risk | L x I = Score | Rating | Recommended treatment |", "|---|---|---|---|---|---|"]
        for f in a.findings:
            lines.append(f"| {f.risk_id} | {f.control['id']} ({f.control['csf']}): {f.answer} | {f.control['risk']} | "
                         f"{f.likelihood} x {f.impact} = {f.score} | {f.rating} | {f.control['fix']} |")
    lines += ["", "## Scoring method", "",
              "Impact is 1 (Public) to 4 (Restricted), plus 1 for operational technology or high business criticality (max 5). "
              "Likelihood is the control's weight (1-3) minus 1, plus 1 if the system is internet-facing, plus 1 if the answer is No rather than Partial (max 5). "
              "Likelihood is at least 1. Score = likelihood x impact: 16+ Critical, 10-15 High, 5-9 Medium, 1-4 Low.", ""]
    return "\n".join(lines)


def risk_briefing(a: Assessment) -> str:
    """One-page summary for the assessment requestor, in plain language."""
    r = a.request
    top = a.findings[:3]
    lines = [
        f"# Risk Briefing: {r.system_name} ({r.request_id})",
        "",
        f"For: {r.requestor}, {r.department}",
        "",
        f"**Bottom line:** overall risk is **{a.overall_rating}**. "
        + (f"{len(a.findings)} gap(s) found; the top {len(top)} are below." if a.findings else "No gaps found; the system can go ahead."),
        "",
    ]
    for i, f in enumerate(top, start=1):
        lines.append(f"{i}. **{f.rating}:** {f.control['risk']} **Action:** {f.control['fix']}")
    lines += ["",
              "**What we need from you:** confirm an owner and target date for each action, and add them to your risk register. "
              "Risks rated High or Critical need sign-off from your department leader if they are accepted rather than fixed.",
              ""]
    return "\n".join(lines)


def summary(assessments: list[Assessment], tracker: IntakeTracker, as_of: date) -> dict:
    intake = intake_rows(assessments, as_of)
    closed = [r for r in intake if r["Completed"]]
    register = register_rows(assessments)
    return {
        "as_of": as_of.isoformat(),
        "requests_received": len(intake) + len(tracker.rejected),
        "requests_accepted": len(intake),
        "requests_rejected": len(tracker.rejected),
        "by_level": dict(Counter(r["Level"] for r in intake)),
        "open": sum(1 for r in intake if not r["Completed"]),
        "overdue": sum(1 for r in intake if r["On time"] == "overdue"),
        "closed_on_time_pct": round(100 * sum(r["On time"] == "yes" for r in closed) / len(closed)) if closed else None,
        "avg_business_days_closed": round(sum(r["Business days"] for r in closed) / len(closed), 1) if closed else None,
        "risks_total": len(register),
        "risks_by_rating": dict(Counter(r["Rating"] for r in register)),
        "compliance_by_function_pct": _portfolio_compliance(assessments),
    }


def _portfolio_compliance(assessments: list[Assessment]) -> dict[str, int]:
    out = {}
    for fn in FUNCTIONS:
        met = total = 0.0
        for a in assessments:
            for c in a.asked:
                if c["function"] == fn:
                    total += 1
                    ans = a.answers[c["id"]]
                    met += 1 if ans == "Yes" else 0.5 if ans == "Partial" else 0
        out[fn] = round(100 * met / total) if total else 0
    return out


def dashboard_html(s: dict, intake: list[dict], register: list[dict]) -> str:
    def bar(label: str, value: int, maxv: int, colour: str = "#1F3A68") -> str:
        width = 0 if maxv == 0 else int(100 * value / maxv)
        return (f'<div class="row"><span class="lbl">{html.escape(label)}</span>'
                f'<span class="bar" style="width:{width}%;background:{colour}"></span><span class="val">{value}</span></div>')

    ratings = ["Critical", "High", "Medium", "Low"]
    by_rating = s["risks_by_rating"]
    top = register[:5]
    sla = ", ".join(f"{k} {v} business days" for k, v in SLA_BUSINESS_DAYS.items())
    parts = [
        "<!DOCTYPE html><html lang='en'><head><meta charset='utf-8'><title>Cyber Risk Dashboard</title>",
        "<style>body{font-family:Segoe UI,Arial,sans-serif;margin:24px;color:#222;max-width:1000px}"
        "h1{color:#1F3A68}.kpis{display:flex;gap:12px;flex-wrap:wrap}.kpi{border:1px solid #ccc;border-radius:8px;padding:12px 16px;min-width:140px}"
        ".kpi b{font-size:28px;display:block}.row{display:flex;align-items:center;gap:8px;margin:4px 0}.lbl{width:120px}"
        ".bar{height:16px;display:inline-block;border-radius:3px}.val{min-width:40px}table{border-collapse:collapse;width:100%;font-size:14px}"
        "td,th{border:1px solid #ddd;padding:6px;text-align:left}th{background:#1F3A68;color:#fff}</style></head><body>",
        f"<h1>Cyber Risk Assessment Dashboard</h1><p>As of {s['as_of']}. Made-up sample data. Targets: {sla}.</p>",
        "<h2>Performance</h2><div class='kpis'>",
        f"<div class='kpi'><b>{s['requests_accepted']}</b>requests accepted</div>",
        f"<div class='kpi'><b>{s['requests_rejected']}</b>sent back to requestor</div>",
        f"<div class='kpi'><b>{s['open']}</b>open ({s['overdue']} overdue)</div>",
        f"<div class='kpi'><b>{s['closed_on_time_pct']}%</b>closed on time</div>",
        f"<div class='kpi'><b>{s['avg_business_days_closed']}</b>avg business days to close</div>",
        "</div><h3>Requests by assessment level</h3>",
    ]
    lv_max = max(s["by_level"].values(), default=0)
    for lv in ["Basic", "Intermediate", "Advanced"]:
        parts.append(bar(lv, s["by_level"].get(lv, 0), lv_max))
    parts.append("<h2>Risk</h2><h3>Risks by rating</h3>")
    r_max = max(by_rating.values(), default=0)
    for rt in ratings:
        parts.append(bar(rt, by_rating.get(rt, 0), r_max, "#" + RATING_COLOURS[rt]))
    parts.append("<h2>Compliance</h2><h3>Questions met by NIST CSF function (%)</h3>")
    for fn, pct in s["compliance_by_function_pct"].items():
        parts.append(bar(fn, pct, 100, "#2E75B6"))
    parts.append("<h3>Top risks</h3><table><tr><th>Risk ID</th><th>System</th><th>Risk</th><th>Score</th><th>Rating</th></tr>")
    for r in top:
        parts.append(f"<tr><td>{r['Risk ID']}</td><td>{html.escape(r['System'])}</td><td>{html.escape(r['Risk'])}</td>"
                     f"<td>{r['Score']}</td><td>{r['Rating']}</td></tr>")
    parts.append("</table><h3>Intake log</h3><table><tr><th>ID</th><th>System</th><th>Level</th><th>Status</th><th>Due</th><th>On time</th><th>Rating</th></tr>")
    for r in intake:
        parts.append(f"<tr><td>{r['Request ID']}</td><td>{html.escape(r['System'])}</td><td>{r['Level']}</td><td>{r['Status']}</td>"
                     f"<td>{r['Due']}</td><td>{r['On time']}</td><td>{r['Overall rating']}</td></tr>")
    parts.append("</table></body></html>")
    return "\n".join(parts)
