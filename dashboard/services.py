from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import requests
from django.conf import settings


ATTENDING = "Attending"
NOT_ATTENDING = "Not Attending"
UNKNOWN = "Unknown"


@dataclass
class DashboardData:
    total_submissions: int
    attending_count: int
    not_attending_count: int
    unknown_count: int
    submissions: list[dict[str, Any]]


def _is_countable_submission(submission: dict[str, Any]) -> bool:
    return str(submission.get("status", "")).strip().upper() != "DELETED"


def _submission_sort_key(submission: dict[str, Any]) -> tuple[str, str, str]:
    return (
        submission.get("created_at", "") or "",
        submission.get("updated_at", "") or "",
        submission.get("id", "") or "",
    )


def _normalized_guest_name(guest_name: str) -> str:
    return " ".join(str(guest_name).strip().lower().split())


def _deduplicate_submissions(submissions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    latest_by_guest: dict[str, dict[str, Any]] = {}

    for submission in submissions:
        guest_key = _normalized_guest_name(submission.get("guest_name", ""))
        existing = latest_by_guest.get(guest_key)

        if existing is None or _submission_sort_key(submission) > _submission_sort_key(existing):
            latest_by_guest[guest_key] = submission

    return list(latest_by_guest.values())


def _normalize_attendance(value: Any) -> str:
    if value is None:
        return UNKNOWN

    normalized = str(value).strip().lower()
    if normalized in {"attending", "yes", "going", "will attend", "attend"}:
        return ATTENDING

    if normalized in {"not attending", "notattending", "no", "cannot attend", "won't attend", "declined"}:
        return NOT_ATTENDING

    if "not" in normalized and "attend" in normalized:
        return NOT_ATTENDING

    if "attend" in normalized or "join" in normalized:
        return ATTENDING

    return UNKNOWN


def _extract_name(answer: dict[str, Any]) -> str:
    if answer.get("prettyFormat"):
        return str(answer["prettyFormat"]).strip()

    raw_answer = answer.get("answer")
    if isinstance(raw_answer, dict):
        parts = [
            raw_answer.get("prefix", ""),
            raw_answer.get("first", ""),
            raw_answer.get("middle", ""),
            raw_answer.get("last", ""),
            raw_answer.get("suffix", ""),
        ]
        return " ".join(part.strip() for part in parts if part and str(part).strip())

    if raw_answer:
        return str(raw_answer).strip()

    return ""


def _parse_submission(submission: dict[str, Any]) -> dict[str, Any]:
    answers = submission.get("answers", {})
    guest_name = ""
    attendance_value = None

    for answer in answers.values():
        prompt = str(answer.get("text", "")).lower()
        answer_name = str(answer.get("name", "")).lower()
        answer_type = str(answer.get("type", "")).lower()

        if not guest_name and (
            answer_type == "control_fullname"
            or "name" in prompt
            or "name" in answer_name
        ):
            guest_name = _extract_name(answer)

        if attendance_value is None and (
            "attend" in prompt
            or "attendance" in prompt
            or "rsvp" in prompt
            or "join" in prompt
            or "coming" in prompt
        ):
            attendance_value = answer.get("answer")

    attendance_status = _normalize_attendance(attendance_value)

    return {
        "id": submission.get("id", ""),
        "created_at": submission.get("created_at", ""),
        "updated_at": submission.get("updated_at") or "",
        "guest_name": guest_name or "Unknown Guest",
        "attendance_status": attendance_status,
        "raw_attendance_value": attendance_value or "",
        "status": submission.get("status", ""),
    }


def fetch_dashboard_data() -> DashboardData:
    response = requests.get(
        f"https://api.jotform.com/form/{settings.JOTFORM_FORM_ID}/submissions",
        params={"apiKey": settings.JOTFORM_API_KEY},
        timeout=settings.JOTFORM_API_TIMEOUT,
    )
    response.raise_for_status()

    payload = response.json()
    submissions = [
        _parse_submission(item)
        for item in payload.get("content", [])
        if _is_countable_submission(item)
    ]
    submissions = _deduplicate_submissions(submissions)

    attending_count = sum(1 for item in submissions if item["attendance_status"] == ATTENDING)
    not_attending_count = sum(1 for item in submissions if item["attendance_status"] == NOT_ATTENDING)
    unknown_count = sum(1 for item in submissions if item["attendance_status"] == UNKNOWN)

    submissions.sort(key=lambda item: item["created_at"], reverse=True)

    return DashboardData(
        total_submissions=len(submissions),
        attending_count=attending_count,
        not_attending_count=not_attending_count,
        unknown_count=unknown_count,
        submissions=submissions,
    )
