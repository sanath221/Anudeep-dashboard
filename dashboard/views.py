from requests import RequestException
from django.shortcuts import render

from .services import ATTENDING, NOT_ATTENDING, fetch_dashboard_data


FILTER_OPTIONS = {
    "all": None,
    "attending": ATTENDING,
    "not-attending": NOT_ATTENDING,
}


def attendance_dashboard(request):
    selected_filter = request.GET.get("status", "all").strip().lower()
    if selected_filter not in FILTER_OPTIONS:
        selected_filter = "all"

    context = {
        "dashboard": None,
        "error_message": "",
        "selected_filter": selected_filter,
        "filtered_submissions": [],
    }

    try:
        dashboard = fetch_dashboard_data()
        target_status = FILTER_OPTIONS[selected_filter]
        filtered_submissions = dashboard.submissions

        if target_status:
            filtered_submissions = [
                submission
                for submission in dashboard.submissions
                if submission["attendance_status"] == target_status
            ]

        context["dashboard"] = dashboard
        context["filtered_submissions"] = filtered_submissions
    except (RequestException, ValueError):
        context["error_message"] = (
            "Unable to load Jotform submissions right now. "
            "Please check the API key, form ID, or network access and try again."
        )

    return render(request, "dashboard/index.html", context)
