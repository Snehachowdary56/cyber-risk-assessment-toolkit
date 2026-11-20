"""Intake tracking: record cyber risk assessment requests, check them and give each an ID."""
from __future__ import annotations

import csv
from dataclasses import dataclass, field
from datetime import date

REQUIRED = ["received", "requestor", "department", "system_name", "description",
            "vendor", "internet_facing", "data_classification", "personal_info",
            "operational_technology", "users", "business_criticality"]
CLASSIFICATIONS = ["Public", "Internal", "Confidential", "Restricted"]
CRITICALITY = ["Low", "Medium", "High"]
YES_NO = {"yes": True, "no": False}
DUPLICATE_WINDOW_DAYS = 90


@dataclass
class Request:
    request_id: str
    received: date
    requestor: str
    department: str
    system_name: str
    description: str
    vendor: bool
    internet_facing: bool
    data_classification: str
    personal_info: bool
    operational_technology: bool
    users: int
    business_criticality: str
    completed: date | None = None
    level: str = ""
    level_reasons: list[str] = field(default_factory=list)


@dataclass
class Rejected:
    row_number: int
    reason: str
    raw: dict


class IntakeError(ValueError):
    pass


def parse_row(row: dict) -> dict:
    """Check one intake row and return clean values. Raises IntakeError with a plain reason."""
    missing = [f for f in REQUIRED if not (row.get(f) or "").strip()]
    if missing:
        raise IntakeError("missing " + ", ".join(missing))
    clean = {k: (v or "").strip() for k, v in row.items()}
    for f in ["vendor", "internet_facing", "personal_info", "operational_technology"]:
        if clean[f].lower() not in YES_NO:
            raise IntakeError(f"{f} must be yes or no")
        clean[f] = YES_NO[clean[f].lower()]
    if clean["data_classification"] not in CLASSIFICATIONS:
        raise IntakeError("unknown data_classification " + clean["data_classification"])
    if clean["business_criticality"] not in CRITICALITY:
        raise IntakeError("unknown business_criticality " + clean["business_criticality"])
    try:
        clean["users"] = int(clean["users"])
        clean["received"] = date.fromisoformat(clean["received"])
        clean["completed"] = date.fromisoformat(clean["completed"]) if clean.get("completed") else None
    except ValueError as exc:
        raise IntakeError(f"bad number or date ({exc})") from exc
    if clean["users"] < 0:
        raise IntakeError("users cannot be negative")
    return clean


class IntakeTracker:
    """Keeps the list of accepted requests and the ones sent back to the requestor."""

    def __init__(self, year: int = 2026):
        self.year = year
        self.requests: list[Request] = []
        self.rejected: list[Rejected] = []

    def add(self, row: dict, row_number: int = 0) -> Request | None:
        try:
            clean = parse_row(row)
        except IntakeError as exc:
            self.rejected.append(Rejected(row_number, str(exc), row))
            return None
        dup = self._find_duplicate(clean)
        if dup:
            self.rejected.append(Rejected(row_number, f"duplicate of {dup.request_id} (same system and requestor within {DUPLICATE_WINDOW_DAYS} days)", row))
            return None
        req = Request(request_id=f"CRA-{self.year}-{len(self.requests) + 1:03d}",
                      **{k: clean[k] for k in REQUIRED}, completed=clean.get("completed"))
        self.requests.append(req)
        return req

    def _find_duplicate(self, clean: dict) -> Request | None:
        for r in self.requests:
            if (r.system_name.lower() == clean["system_name"].lower()
                    and r.requestor.lower() == clean["requestor"].lower()
                    and abs((clean["received"] - r.received).days) <= DUPLICATE_WINDOW_DAYS):
                return r
        return None

    def load_csv(self, path: str) -> None:
        with open(path, newline="", encoding="utf-8") as fh:
            for i, row in enumerate(csv.DictReader(fh), start=2):
                self.add(row, row_number=i)
