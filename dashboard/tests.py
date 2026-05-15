from unittest.mock import Mock, patch

from django.test import TestCase
from django.urls import reverse

from .services import ATTENDING, NOT_ATTENDING, TENTATIVE, UNKNOWN, _parse_submission, fetch_dashboard_data


class SubmissionParsingTests(TestCase):
    def test_parse_submission_extracts_name_and_attendance(self):
        submission = {
            "id": "123",
            "created_at": "2026-04-11 20:00:56",
            "status": "ACTIVE",
            "answers": {
                "2": {
                    "text": "Member Name",
                    "type": "control_fullname",
                    "prettyFormat": "Kundhan Vallamkonda",
                },
                "6": {
                    "text": "Will you attend?",
                    "type": "control_radio",
                    "answer": "Attending",
                },
            },
        }

        parsed = _parse_submission(submission)

        self.assertEqual(parsed["guest_name"], "Kundhan Vallamkonda")
        self.assertEqual(parsed["attendance_status"], ATTENDING)

    def test_parse_submission_extracts_multiple_attendance_questions(self):
        submission = {
            "id": "124",
            "created_at": "2026-04-11 21:00:00",
            "status": "ACTIVE",
            "answers": {
                "2": {
                    "text": "Member Name",
                    "type": "control_fullname",
                    "prettyFormat": "Guest Example",
                },
                "6": {
                    "text": "Will you attend?",
                    "type": "control_radio",
                    "answer": "Attending",
                },
                "7": {
                    "text": "Will your partner join?",
                    "type": "control_radio",
                    "answer": "No",
                },
            },
        }

        parsed = _parse_submission(submission)

        self.assertEqual(parsed["attendance_status"], ATTENDING)
        self.assertEqual(len(parsed["attendance_answers"]), 2)
        self.assertEqual(parsed["attendance_answers"][0]["attendance_status"], ATTENDING)
        self.assertEqual(parsed["attendance_answers"][1]["attendance_status"], NOT_ATTENDING)

    def test_parse_submission_handles_decline_values(self):
        submission = {
            "id": "124",
            "created_at": "2026-04-11 20:00:56",
            "status": "ACTIVE",
            "answers": {
                "2": {
                    "text": "Member Name",
                    "type": "control_fullname",
                    "prettyFormat": "Guest Example",
                },
                "6": {
                    "text": "Will you attend?",
                    "type": "control_radio",
                    "answer": "Not Attending",
                },
            },
        }

        parsed = _parse_submission(submission)

        self.assertEqual(parsed["attendance_status"], NOT_ATTENDING)

    def test_parse_submission_handles_tentative_values(self):
        submission = {
            "id": "126",
            "created_at": "2026-04-11 22:00:00",
            "status": "ACTIVE",
            "answers": {
                "2": {
                    "text": "Member Name",
                    "type": "control_fullname",
                    "prettyFormat": "Tentative Guest",
                },
                "6": {
                    "text": "Haldi (June 27th, 8:30 AM CST)?",
                    "type": "control_radio",
                    "answer": "Tentative",
                },
            },
        }

        parsed = _parse_submission(submission)

        self.assertEqual(parsed["attendance_status"], TENTATIVE)
        self.assertEqual(parsed["attendance_answers"][0]["attendance_status"], TENTATIVE)

    def test_parse_submission_marks_unknown_without_attendance_answer(self):
        submission = {
            "id": "125",
            "created_at": "2026-04-11 20:00:56",
            "status": "ACTIVE",
            "answers": {
                "2": {
                    "text": "Member Name",
                    "type": "control_fullname",
                    "prettyFormat": "Unknown Example",
                },
            },
        }

        parsed = _parse_submission(submission)

        self.assertEqual(parsed["attendance_status"], UNKNOWN)


class DashboardViewTests(TestCase):
    @patch("dashboard.services.requests.get")
    def test_fetch_dashboard_data_returns_summary_counts(self, mock_get):
        mock_response = Mock()
        mock_response.json.return_value = {
            "content": [
                {
                    "id": "1",
                    "created_at": "2026-04-11 20:00:56",
                    "status": "ACTIVE",
                    "answers": {
                        "2": {
                            "text": "Member Name",
                            "type": "control_fullname",
                            "prettyFormat": "Person One",
                        },
                        "6": {
                            "text": "Will you attend?",
                            "type": "control_radio",
                            "answer": "Attending",
                        },
                    },
                },
                {
                    "id": "2",
                    "created_at": "2026-04-11 18:00:00",
                    "status": "ACTIVE",
                    "answers": {
                        "2": {
                            "text": "Member Name",
                            "type": "control_fullname",
                            "prettyFormat": "Person Two",
                        },
                        "6": {
                            "text": "Will you attend?",
                            "type": "control_radio",
                            "answer": "Not Attending",
                        },
                    },
                },
            ]
        }
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        dashboard = fetch_dashboard_data()

        self.assertEqual(dashboard.total_submissions, 2)
        self.assertEqual(dashboard.attending_count, 1)
        self.assertEqual(dashboard.not_attending_count, 1)
        self.assertEqual(dashboard.tentative_count, 0)
        self.assertEqual(dashboard.unknown_count, 0)
        self.assertIn("Will you attend?", dashboard.question_summary)

    @patch("dashboard.services.requests.get")
    def test_fetch_dashboard_data_ignores_deleted_submissions(self, mock_get):
        mock_response = Mock()
        mock_response.json.return_value = {
            "content": [
                {
                    "id": "1",
                    "created_at": "2026-04-11 20:00:56",
                    "status": "ACTIVE",
                    "answers": {
                        "2": {
                            "text": "Member Name",
                            "type": "control_fullname",
                            "prettyFormat": "Visible Guest",
                        },
                        "6": {
                            "text": "Will you attend?",
                            "type": "control_radio",
                            "answer": "Attending",
                        },
                    },
                },
                {
                    "id": "2",
                    "created_at": "2026-04-11 21:00:00",
                    "status": "DELETED",
                    "answers": {
                        "2": {
                            "text": "Member Name",
                            "type": "control_fullname",
                            "prettyFormat": "Deleted Guest",
                        },
                        "6": {
                            "text": "Will you attend?",
                            "type": "control_radio",
                            "answer": "Not Attending",
                        },
                    },
                },
            ]
        }
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        dashboard = fetch_dashboard_data()

        self.assertEqual(dashboard.total_submissions, 1)
        self.assertEqual(dashboard.attending_count, 1)
        self.assertEqual(dashboard.not_attending_count, 0)
        self.assertEqual(dashboard.tentative_count, 0)
        self.assertEqual(dashboard.submissions[0]["guest_name"], "Visible Guest")
        self.assertEqual(dashboard.question_summary["Will you attend?"].get("attending"), 1)

    @patch("dashboard.services.requests.get")
    def test_fetch_dashboard_data_keeps_only_latest_duplicate_guest(self, mock_get):
        mock_response = Mock()
        mock_response.json.return_value = {
            "content": [
                {
                    "id": "1",
                    "created_at": "2026-04-11 18:00:00",
                    "status": "ACTIVE",
                    "answers": {
                        "2": {
                            "text": "Member Name",
                            "type": "control_fullname",
                            "prettyFormat": "Repeat Guest",
                        },
                        "6": {
                            "text": "Will you attend?",
                            "type": "control_radio",
                            "answer": "Attending",
                        },
                    },
                },
                {
                    "id": "2",
                    "created_at": "2026-04-11 20:00:00",
                    "status": "ACTIVE",
                    "answers": {
                        "2": {
                            "text": "Member Name",
                            "type": "control_fullname",
                            "prettyFormat": "Repeat Guest",
                        },
                        "6": {
                            "text": "Will you attend?",
                            "type": "control_radio",
                            "answer": "Not Attending",
                        },
                    },
                },
                {
                    "id": "3",
                    "created_at": "2026-04-11 19:00:00",
                    "status": "ACTIVE",
                    "answers": {
                        "2": {
                            "text": "Member Name",
                            "type": "control_fullname",
                            "prettyFormat": "Unique Guest",
                        },
                        "6": {
                            "text": "Will you attend?",
                            "type": "control_radio",
                            "answer": "Attending",
                        },
                    },
                },
            ]
        }
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        dashboard = fetch_dashboard_data()

        self.assertEqual(dashboard.total_submissions, 2)
        self.assertEqual(dashboard.attending_count, 1)
        self.assertEqual(dashboard.not_attending_count, 1)
        self.assertEqual(dashboard.submissions[0]["guest_name"], "Repeat Guest")
        self.assertEqual(dashboard.submissions[0]["attendance_status"], NOT_ATTENDING)

    @patch("dashboard.views.fetch_dashboard_data")
    def test_dashboard_page_renders(self, mock_fetch_dashboard_data):
        mock_fetch_dashboard_data.return_value = Mock(
            total_submissions=2,
            attending_count=1,
            not_attending_count=1,
            tentative_count=0,
            unknown_count=0,
            question_summary={},
            submissions=[
                {
                    "guest_name": "Attending Guest",
                    "attendance_status": ATTENDING,
                    "attendance_answers": [
                        {"question_label": "Will you attend?", "attendance_status": ATTENDING},
                    ],
                    "created_at": "2026-04-11 20:00:56",
                    "status": "ACTIVE",
                },
                {
                    "guest_name": "Declined Guest",
                    "attendance_status": NOT_ATTENDING,
                    "attendance_answers": [
                        {"question_label": "Will you attend?", "attendance_status": NOT_ATTENDING},
                    ],
                    "created_at": "2026-04-11 19:00:00",
                    "status": "ACTIVE",
                },
            ],
        )

        response = self.client.get(reverse("attendance-dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Attendance Dashboard")

    @patch("dashboard.views.fetch_dashboard_data")
    def test_dashboard_page_filters_attending_submissions(self, mock_fetch_dashboard_data):
        mock_fetch_dashboard_data.return_value = Mock(
            total_submissions=2,
            attending_count=1,
            not_attending_count=1,
            tentative_count=0,
            unknown_count=0,
            question_summary={},
            submissions=[
                {
                    "guest_name": "Attending Guest",
                    "attendance_status": ATTENDING,
                    "attendance_answers": [
                        {"question_label": "Will you attend?", "attendance_status": ATTENDING},
                    ],
                    "created_at": "2026-04-11 20:00:56",
                    "status": "ACTIVE",
                },
                {
                    "guest_name": "Declined Guest",
                    "attendance_status": NOT_ATTENDING,
                    "attendance_answers": [
                        {"question_label": "Will you attend?", "attendance_status": NOT_ATTENDING},
                    ],
                    "created_at": "2026-04-11 19:00:00",
                    "status": "ACTIVE",
                },
            ],
        )

        response = self.client.get(reverse("attendance-dashboard"), {"status": "attending"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Attending Guest")
        self.assertNotContains(response, "Declined Guest")

    @patch("dashboard.views.fetch_dashboard_data")
    def test_dashboard_page_filters_not_attending_submissions(self, mock_fetch_dashboard_data):
        mock_fetch_dashboard_data.return_value = Mock(
            total_submissions=2,
            attending_count=1,
            not_attending_count=1,
            tentative_count=0,
            unknown_count=0,
            question_summary={},
            submissions=[
                {
                    "guest_name": "Attending Guest",
                    "attendance_status": ATTENDING,
                    "attendance_answers": [
                        {"question_label": "Will you attend?", "attendance_status": ATTENDING},
                    ],
                    "created_at": "2026-04-11 20:00:56",
                    "status": "ACTIVE",
                },
                {
                    "guest_name": "Declined Guest",
                    "attendance_status": NOT_ATTENDING,
                    "attendance_answers": [
                        {"question_label": "Will you attend?", "attendance_status": NOT_ATTENDING},
                    ],
                    "created_at": "2026-04-11 19:00:00",
                    "status": "ACTIVE",
                },
            ],
        )

        response = self.client.get(reverse("attendance-dashboard"), {"status": "not-attending"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Declined Guest")
        self.assertNotContains(response, "Attending Guest")
