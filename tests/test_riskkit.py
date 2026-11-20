import csv
import json
from datetime import date
from pathlib import Path

import pytest
from openpyxl import load_workbook

from riskkit.assessment import assess, impact_score, load_controls, questions_for, rating
from riskkit.cli import run
from riskkit.intake import IntakeError, IntakeTracker, parse_row
from riskkit.triage import add_business_days, assign_level, business_days_between

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"


def read_csv(path):
    return list(csv.DictReader(path.read_text(encoding="utf-8").splitlines()))


def row(**over):
    base = {"received": "2026-11-02", "requestor": "Test User", "department": "IT", "system_name": "Test App",
            "description": "test", "vendor": "no", "internet_facing": "no", "data_classification": "Internal",
            "personal_info": "no", "operational_technology": "no", "users": "10", "business_criticality": "Low",
            "completed": ""}
    base.update(over)
    return base


def accepted(**over):
    t = IntakeTracker()
    req = t.add(row(**over))
    assert req is not None, t.rejected
    req.level, req.level_reasons = assign_level(req)
    return req


@pytest.fixture(scope="module")
def controls():
    return load_controls(str(DATA / "controls.json"))


@pytest.fixture(scope="module")
def output(tmp_path_factory):
    out = tmp_path_factory.mktemp("out")
    s = run(DATA / "sample_requests.csv", DATA / "sample_answers.json", DATA / "controls.json", out, date(2026, 11, 19))
    return out, s


# ---------- intake ----------

def test_intake_assigns_sequential_ids():
    t = IntakeTracker(year=2027)
    a = t.add(row(system_name="A"))
    b = t.add(row(system_name="B"))
    assert (a.request_id, b.request_id) == ("CRA-2027-001", "CRA-2027-002")


@pytest.mark.parametrize("over, reason", [
    ({"requestor": ""}, "missing requestor"),
    ({"vendor": "maybe"}, "vendor must be yes or no"),
    ({"data_classification": "Secret"}, "unknown data_classification"),
    ({"users": "lots"}, "bad number or date"),
    ({"received": "19/11/2026"}, "bad number or date"),
    ({"users": "-5"}, "users cannot be negative"),
])
def test_intake_rejects_bad_rows_with_reason(over, reason):
    with pytest.raises(IntakeError, match=reason):
        parse_row(row(**over))


def test_intake_flags_duplicate_within_window_only():
    t = IntakeTracker()
    t.add(row(received="2026-09-01"))
    assert t.add(row(received="2026-10-15")) is None
    assert "duplicate of CRA-2026-001" in t.rejected[0].reason
    assert t.add(row(received="2027-01-15")) is not None  # more than 90 days later is a new request


# ---------- assessment level assignment ----------

def test_low_risk_request_is_basic():
    assert accepted().level == "Basic"


def test_confidential_vendor_internet_personal_is_intermediate():
    req = accepted(data_classification="Confidential", vendor="yes", internet_facing="yes", personal_info="yes")
    assert req.level == "Intermediate"
    assert req.level_reasons[0] == "5 points"


def test_operational_technology_is_never_basic():
    req = accepted(operational_technology="yes", data_classification="Public")
    assert req.level == "Intermediate"
    assert any("never assessed at Basic" in r for r in req.level_reasons)


def test_high_criticality_operational_technology_is_advanced():
    assert accepted(operational_technology="yes", business_criticality="High").level == "Advanced"


def test_restricted_personal_information_is_advanced():
    assert accepted(data_classification="Restricted", personal_info="yes").level == "Advanced"


# ---------- questionnaire and scoring ----------

def test_higher_levels_ask_more_questions(controls):
    counts = [len(questions_for(lv, controls)) for lv in ["Basic", "Intermediate", "Advanced"]]
    assert counts[0] < counts[1] < counts[2] == len(controls)


def test_every_control_maps_to_a_nist_csf_category(controls):
    prefix = {"Govern": "GV", "Identify": "ID", "Protect": "PR", "Detect": "DE", "Respond": "RS", "Recover": "RC"}
    for c in controls:
        assert c["csf"].split(".")[0] == prefix[c["function"]]
        assert c["id"].startswith(prefix[c["function"]])
        assert c["risk"] and c["fix"]


def test_impact_and_rating_bands():
    assert impact_score(accepted(data_classification="Public")) == 1
    assert impact_score(accepted(data_classification="Restricted", business_criticality="High")) == 5
    assert [rating(s) for s in (4, 5, 9, 10, 15, 16, 25)] == ["Low", "Medium", "Medium", "High", "High", "Critical", "Critical"]


def test_no_answer_scores_higher_than_partial(controls):
    req = accepted(data_classification="Confidential")
    no = assess(req, controls, {"PR-01": "No"}).findings[0]
    partial = assess(req, controls, {"PR-01": "Partial"}).findings[0]
    assert no.likelihood == partial.likelihood + 1
    assert no.score > partial.score


def test_no_gaps_means_no_findings_and_low_rating(controls):
    a = assess(accepted(), controls, {})
    assert a.findings == [] and a.overall_rating == "Low" and a.compliance == 1.0


def test_answer_for_question_not_asked_at_level_is_an_error(controls):
    with pytest.raises(ValueError, match="not asked at Basic level"):
        assess(accepted(), controls, {"DE-02": "No"})


def test_invalid_answer_is_an_error(controls):
    with pytest.raises(ValueError, match="must be one of"):
        assess(accepted(), controls, {"PR-01": "Maybe"})


def test_compliance_by_function_counts_partial_as_half(controls):
    a = assess(accepted(), controls, {"PR-01": "Partial"})
    protect = [c for c in a.asked if c["function"] == "Protect"]
    assert a.compliance_by_function()["Protect"] == pytest.approx((len(protect) - 0.5) / len(protect))
    assert a.compliance_by_function()["Detect"] is None  # not asked at Basic


# ---------- business days ----------

def test_business_days_skip_weekends():
    friday = date(2026, 11, 13)
    assert add_business_days(friday, 1) == date(2026, 11, 16)
    assert business_days_between(friday, date(2026, 11, 20)) == 5


# ---------- end to end on the sample data ----------

def test_sample_run_counts(output):
    _, s = output
    assert s["requests_received"] == 14
    assert s["requests_accepted"] == 12
    assert s["requests_rejected"] == 2
    assert s["by_level"] == {"Basic": 3, "Intermediate": 4, "Advanced": 5}
    assert s["risks_total"] == 29
    assert s["open"] == 4 and s["overdue"] == 3
    assert s["closed_on_time_pct"] == 75


def test_sample_rejections_explain_why(output):
    out, _ = output
    rows = list(read_csv(out / "rejected_requests.csv"))
    reasons = sorted(r["Reason"] for r in rows)
    assert reasons[0].startswith("duplicate of CRA-2026-001")
    assert reasons[1] == "missing requestor"


def test_fleet_management_is_the_top_critical_risk(output):
    out, _ = output
    rows = list(read_csv(out / "risk_register.csv"))
    assert rows[0]["System"] == "Haul Truck Fleet Management"
    assert rows[0]["Rating"] == "Critical"
    scores = [int(r["Score"]) for r in rows]
    assert scores == sorted(scores, reverse=True)


def test_register_score_equals_likelihood_times_impact(output):
    out, _ = output
    for r in read_csv(out / "risk_register.csv"):
        assert int(r["Score"]) == int(r["Likelihood"]) * int(r["Impact"])


def test_excel_register_has_both_sheets_and_colours(output):
    out, s = output
    wb = load_workbook(out / "risk_register.xlsx")
    assert wb.sheetnames == ["Risk Register", "Intake Log"]
    ws = wb["Risk Register"]
    assert ws.max_row == s["risks_total"] + 1
    assert ws.freeze_panes == "A2"
    rating_col = [c.value for c in ws[1]].index("Rating") + 1
    assert ws.cell(row=2, column=rating_col).fill.fgColor.rgb.endswith("C00000")


def test_every_request_gets_a_report_and_a_briefing(output):
    out, s = output
    assert len(list((out / "reports").glob("*.md"))) == s["requests_accepted"]
    assert len(list((out / "briefings").glob("*.md"))) == s["requests_accepted"]
    report = (out / "reports" / "CRA-2026-007.md").read_text(encoding="utf-8")
    assert "Overall risk rating:** Critical" in report and "NIST Cybersecurity Framework" in report
    briefing = (out / "briefings" / "CRA-2026-007_briefing.md").read_text(encoding="utf-8")
    assert briefing.count("**Action:**") == 3


def test_dashboard_shows_performance_and_compliance(output):
    out, s = output
    page = (out / "dashboard.html").read_text(encoding="utf-8")
    for text in ["Performance", "Compliance", "closed on time", "Top risks", "Intake log"]:
        assert text in page
    assert json.loads((out / "summary.json").read_text())["risks_total"] == s["risks_total"]
