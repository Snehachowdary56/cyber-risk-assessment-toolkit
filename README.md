# Cyber Risk Assessment Toolkit

![CI](https://github.com/Snehachowdary56/cyber-risk-assessment-toolkit/actions/workflows/ci.yml/badge.svg)

When a team wants a new system, such as a cloud app, a vendor portal or an upgrade to equipment at a mine site, a cyber risk team checks it first. This toolkit runs that process from start to finish: **intake → assessment level → questionnaire → scored risks → briefing, report and risk register → dashboard for senior leaders**.

**Live dashboard:** https://snehachowdary56.github.io/cyber-risk-assessment-toolkit/

> **Data note:** every request, person and answer here is **made-up sample data**.

## What it does

| Step | What happens | Output |
|---|---|---|
| 1. Intake tracking | Each cyber risk assessment request gets an ID (CRA-2026-001). Requests with missing or bad fields, and duplicates within 90 days, go back to the requestor with the reason. | `intake_log.csv`, `rejected_requests.csv` |
| 2. Assessment level assignment | Points for data classification, personal information, internet exposure, vendor, operational technology, user count and criticality decide **Basic**, **Intermediate** or **Advanced**. Some rules always apply, for example high-criticality operational technology is always Advanced. | level and reasons in the intake log |
| 3. Questionnaire | 18 questions mapped to the **NIST Cybersecurity Framework 2.0** functions (Govern, Identify, Protect, Detect, Respond, Recover). Basic asks 6, Intermediate 12, Advanced all 18. | |
| 4. Risk scoring | Each "No" or "Partial" answer becomes a risk: **likelihood x impact** = score, rated Low, Medium, High or Critical, with a recommended treatment. | `risk_register.csv`, `risk_register.xlsx` |
| 5. Risk assessment report | Scope, results by NIST CSF function, findings and the scoring method. | `reports/CRA-*.md` |
| 6. Risk briefing | A one-page summary for the requestor: the bottom line, the top 3 risks and what they need to do. | `briefings/CRA-*_briefing.md` |
| 7. Dashboard | **Performance** (requests by level, open, overdue, % closed on time, average turnaround) and **compliance** (% of questions met by NIST CSF function), plus top risks. | `dashboard.html`, `summary.json` |

## Results on the sample data

- **14** requests received: **12** accepted, **2** sent back (one missing the requestor's name, one duplicate)
- Levels: **3 Basic, 4 Intermediate, 5 Advanced**
- **29** risks in the register: 3 Critical, 15 High, 9 Medium, 2 Low
- Top risk: the **Haul Truck Fleet Management** system (operational technology, internet-facing, no MFA and no network separation)
- **75%** of closed requests finished within target; **3** open requests are overdue
- Weakest NIST CSF function across all systems: **Detect** (security logs and alerts)

## How a risk is scored

- **Impact** (1 to 5): Public 1, Internal 2, Confidential 3, Restricted 4, plus 1 for operational technology or high business criticality.
- **Likelihood** (1 to 5): the control's weight (1 to 3) minus 1, plus 1 if the system is internet-facing, plus 1 if the answer is "No" rather than "Partial".
- **Score** = likelihood x impact: 16+ Critical, 10 to 15 High, 5 to 9 Medium, 1 to 4 Low.

Target turnaround: Basic 5, Intermediate 10, Advanced 20 business days.

## The 3 lines of defense

The toolkit is built for the **2nd line of defense** (the risk team acting as facilitator), working with the **1st line** (the teams that own the systems). See [docs/three_lines_of_defense.md](docs/three_lines_of_defense.md).

## Run it (Windows Command Prompt)

```
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
pytest -q
python -m riskkit
```

Outputs go to the `output` folder. Open `output\dashboard.html` in a browser and `output\risk_register.xlsx` in Excel.

Use your own files: `python -m riskkit --requests my_requests.csv --answers my_answers.json --as-of 2027-01-15`

## Tests

29 automated tests check intake validation and duplicates, level rules, question counts per level, NIST CSF mapping, scoring and ratings, business-day targets, the Excel register, and the full run on the sample data. GitHub Actions runs them on Python 3.11 and 3.12 on every push, runs the tool, and publishes the dashboard.

## Terms in plain language

- **Cyber risk assessment**: a check of how likely a system is to be attacked or fail, and how bad it would be.
- **Risk register**: the list of known risks, each with an owner, a rating and a plan.
- **NIST Cybersecurity Framework (CSF)**: a widely used guide from the U.S. National Institute of Standards and Technology that groups security work into six functions.
- **Operational technology (OT)**: systems that control physical equipment, such as mill sensors or remote drills.
- **MFA**: multi-factor authentication, a second check such as a phone code when signing in.
