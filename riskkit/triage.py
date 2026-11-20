"""Assessment level assignment: decide if a request needs a Basic, Intermediate or Advanced Assessment."""
from __future__ import annotations

from datetime import date, timedelta

from .intake import CLASSIFICATIONS, Request

LEVELS = ["Basic", "Intermediate", "Advanced"]
# Target turnaround in business days for each assessment level.
SLA_BUSINESS_DAYS = {"Basic": 5, "Intermediate": 10, "Advanced": 20}


def assign_level(req: Request) -> tuple[str, list[str]]:
    """Return the assessment level and the reasons behind it, in plain language."""
    points = 0
    reasons: list[str] = []

    cls_points = CLASSIFICATIONS.index(req.data_classification)  # Public 0 ... Restricted 3
    if cls_points:
        points += cls_points
        reasons.append(f"{req.data_classification} data (+{cls_points})")
    if req.personal_info:
        points += 1
        reasons.append("holds personal information (+1)")
    if req.internet_facing:
        points += 1
        reasons.append("reachable from the internet (+1)")
    if req.vendor:
        points += 1
        reasons.append("third-party vendor involved (+1)")
    if req.operational_technology:
        points += 2
        reasons.append("connects to operational technology at a site (+2)")
    if req.users > 500:
        points += 1
        reasons.append(f"{req.users} users (+1)")
    if req.business_criticality == "High":
        points += 1
        reasons.append("high business criticality (+1)")

    if points >= 7:
        level = "Advanced"
    elif points >= 3:
        level = "Intermediate"
    else:
        level = "Basic"

    # Floors that apply whatever the points say.
    if req.operational_technology and level == "Basic":
        level = "Intermediate"
        reasons.append("operational technology is never assessed at Basic")
    if req.operational_technology and req.business_criticality == "High" and level != "Advanced":
        level = "Advanced"
        reasons.append("high-criticality operational technology always gets an Advanced Assessment")
    if req.data_classification == "Restricted" and req.personal_info and level != "Advanced":
        level = "Advanced"
        reasons.append("Restricted personal information always gets an Advanced Assessment")

    reasons.insert(0, f"{points} points")
    return level, reasons


def add_business_days(start: date, days: int) -> date:
    d = start
    added = 0
    while added < days:
        d += timedelta(days=1)
        if d.weekday() < 5:
            added += 1
    return d


def business_days_between(start: date, end: date) -> int:
    count = 0
    d = start
    while d < end:
        d += timedelta(days=1)
        if d.weekday() < 5:
            count += 1
    return count


def due_date(req: Request) -> date:
    return add_business_days(req.received, SLA_BUSINESS_DAYS[req.level])
