"""Run the questionnaire for a request and turn the gaps into scored risks."""
from __future__ import annotations

import json
from dataclasses import dataclass, field

from .intake import CLASSIFICATIONS, Request
from .triage import LEVELS

ANSWERS = ["Yes", "Partial", "No"]
FUNCTIONS = ["Govern", "Identify", "Protect", "Detect", "Respond", "Recover"]


def load_controls(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as fh:
        controls = json.load(fh)
    ids = [c["id"] for c in controls]
    if len(ids) != len(set(ids)):
        raise ValueError("control IDs must be unique")
    for c in controls:
        if c["level"] not in LEVELS or c["function"] not in FUNCTIONS:
            raise ValueError(f"bad level or function in {c['id']}")
    return controls


def questions_for(level: str, controls: list[dict]) -> list[dict]:
    """A Basic Assessment asks the Basic questions; higher levels add their own on top."""
    upto = LEVELS.index(level)
    return [c for c in controls if LEVELS.index(c["level"]) <= upto]


def impact_score(req: Request) -> int:
    """1 (Public) to 4 (Restricted), plus 1 for operational technology or high criticality; max 5."""
    impact = CLASSIFICATIONS.index(req.data_classification) + 1
    if req.operational_technology or req.business_criticality == "High":
        impact += 1
    return min(impact, 5)


def rating(score: int) -> str:
    if score >= 16:
        return "Critical"
    if score >= 10:
        return "High"
    if score >= 5:
        return "Medium"
    return "Low"


@dataclass
class Finding:
    risk_id: str
    control: dict
    answer: str
    likelihood: int
    impact: int

    @property
    def score(self) -> int:
        return self.likelihood * self.impact

    @property
    def rating(self) -> str:
        return rating(self.score)


@dataclass
class Assessment:
    request: Request
    asked: list[dict]
    answers: dict[str, str]
    findings: list[Finding] = field(default_factory=list)

    def compliance_by_function(self) -> dict[str, float | None]:
        """Share of questions met per NIST CSF function; Partial counts as half."""
        result: dict[str, float | None] = {}
        for fn in FUNCTIONS:
            qs = [c for c in self.asked if c["function"] == fn]
            if not qs:
                result[fn] = None
                continue
            met = sum(1 if self.answers[c["id"]] == "Yes" else 0.5 if self.answers[c["id"]] == "Partial" else 0 for c in qs)
            result[fn] = met / len(qs)
        return result

    @property
    def compliance(self) -> float:
        met = sum(1 if a == "Yes" else 0.5 if a == "Partial" else 0 for a in self.answers.values())
        return met / len(self.answers) if self.answers else 1.0

    @property
    def overall_rating(self) -> str:
        if not self.findings:
            return "Low"
        return max(self.findings, key=lambda f: f.score).rating

    @property
    def top_score(self) -> int:
        return max((f.score for f in self.findings), default=0)


def assess(req: Request, controls: list[dict], gaps: dict[str, str]) -> Assessment:
    """gaps lists answers that are not 'Yes'. A gap for a question not asked at this level is an error."""
    asked = questions_for(req.level, controls)
    asked_ids = {c["id"] for c in asked}
    unknown = set(gaps) - asked_ids
    if unknown:
        raise ValueError(f"{req.request_id}: answers for questions not asked at {req.level} level: {sorted(unknown)}")
    for cid, ans in gaps.items():
        if ans not in ANSWERS:
            raise ValueError(f"{req.request_id}: answer for {cid} must be one of {ANSWERS}")
    answers = {c["id"]: gaps.get(c["id"], "Yes") for c in asked}

    a = Assessment(request=req, asked=asked, answers=answers)
    impact = impact_score(req)
    n = 0
    for c in asked:
        ans = answers[c["id"]]
        if ans == "Yes":
            continue
        likelihood = c["weight"] - 1 + (1 if req.internet_facing else 0) + (1 if ans == "No" else 0)
        n += 1
        a.findings.append(Finding(f"{req.request_id}-R{n:02d}", c, ans, min(max(likelihood, 1), 5), impact))
    a.findings.sort(key=lambda f: (-f.score, f.risk_id))
    return a
