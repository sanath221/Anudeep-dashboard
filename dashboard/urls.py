from django.urls import path

from .views import attendance_dashboard

urlpatterns = [
    path("", attendance_dashboard, name="attendance-dashboard"),
]
