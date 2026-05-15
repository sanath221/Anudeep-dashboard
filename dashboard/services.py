from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import requests
from django.conf import settings


ATTENDING = "Attending"
NOT_ATTENDING = "Not Attending"
TENTATIVE = "Tentative"
UNKNOWN = "Unknown"


@dataclass
class DashboardData:
    total_submissions: int
    attending_count: int
    not_attending_count: int
    tentative_count: int
    unknown_count: int
    submissions: list[dict[str, Any]]
    question_summary: dict[str, dict[str, int]]


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
    if normalized in {"attending", "attend", "yes", "going", "will attend", "yes please", "sure"}:
        return ATTENDING

    if normalized in {"not attending", "notattending", "no", "cannot attend", "won't attend", "declined", "not going"}:
        return NOT_ATTENDING

    if normalized in {"tentative", "maybe", "unsure", "not sure", "possibly", "may be"}:
        return TENTATIVE

    if "not" in normalized and "attend" in normalized:
        return NOT_ATTENDING

    if "tentative" in normalized or "maybe" in normalized:
        return TENTATIVE

    if "attend" in normalized or "join" in normalized:
        return ATTENDING

    return UNKNOWN


def _is_attendance_question(answer: dict[str, Any]) -> bool:
    prompt = str(answer.get("text", "")).strip().lower()
    answer_name = str(answer.get("name", "")).strip().lower()
    
    excluded_keywords = ("kundhan & varshini", "kundhan and varshini", "submit rsvp", "submit response", "wedding events")
    if any(keyword in prompt for keyword in excluded_keywords) or any(keyword in answer_name for keyword in excluded_keywords):
        return False
    
    attendance_keywords = ("attend", "attendance", "rsvp", "join", "coming", "going")
    event_keywords = ("haldi", "mehandi", "mehendi", "pelli", "wedding", "koduku", "kuthuru")

    has_attendance_keyword = any(keyword in prompt for keyword in attendance_keywords) or any(keyword in answer_name for keyword in attendance_keywords)
    has_event_keyword = any(keyword in prompt for keyword in event_keywords) or any(keyword in answer_name for keyword in event_keywords)

    return has_attendance_keyword or has_event_keyword


def _extract_attendance_answers(answers: dict[str, Any]) -> list[dict[str, Any]]:
    attendance_answers: list[dict[str, Any]] = []

    for answer in answers.values():
        if not isinstance(answer, dict):
            continue

        if not _is_attendance_question(answer):
            continue

        question_label = str(answer.get("text") or answer.get("name") or "Attendance response").strip()
        answer_value = answer.get("answer")
        attendance_status = _normalize_attendance(answer_value)

        attendance_answers.append(
            {
                "question_label": question_label,
                "attendance_status": attendance_status,
                "raw_answer": answer_value or "",
            }
        )

    if not attendance_answers:
        attendance_answers.append(
            {
                "question_label": "Attendance response",
                "attendance_status": UNKNOWN,
                "raw_answer": "",
            }
        )

    return attendance_answers


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

    attendance_answers = _extract_attendance_answers(answers)
    attendance_status = attendance_answers[0]["attendance_status"]

    return {
        "id": submission.get("id", ""),
        "created_at": submission.get("created_at", ""),
        "updated_at": submission.get("updated_at") or "",
        "guest_name": guest_name or "Unknown Guest",
        "attendance_status": attendance_status,
        "attendance_answers": attendance_answers,
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
    tentative_count = sum(1 for item in submissions if item["attendance_status"] == TENTATIVE)
    unknown_count = sum(1 for item in submissions if item["attendance_status"] == UNKNOWN)

    question_summary: dict[str, dict[str, int]] = {}
    for item in submissions:
        for answer in item["attendance_answers"]:
            label = answer["question_label"]
            question_summary.setdefault(label, {"attending": 0, "not_attending": 0, "tentative": 0, "unknown": 0})
            if answer["attendance_status"] == ATTENDING:
                question_summary[label]["attending"] += 1
            elif answer["attendance_status"] == NOT_ATTENDING:
                question_summary[label]["not_attending"] += 1
            elif answer["attendance_status"] == TENTATIVE:
                question_summary[label]["tentative"] += 1
            else:
                question_summary[label]["unknown"] += 1

    submissions.sort(key=lambda item: item["created_at"], reverse=True)

    return DashboardData(
        total_submissions=len(submissions),
        attending_count=attending_count,
        not_attending_count=not_attending_count,
        tentative_count=tentative_count,
        unknown_count=unknown_count,
        submissions=submissions,
        question_summary=question_summary,
    )
