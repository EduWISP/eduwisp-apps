# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Michele Salerno e i contributori di EduWISP
"""Da includere nel progetto: path("", include("eduwisp_apps.urls"))."""

from django.urls import path

from .views import ApkView, AppRequestView

app_name = "eduwisp_apps"

urlpatterns = [
    path("api/protocol/v0/apps/<int:pk>/apk", ApkView.as_view(), name="apk"),
    path("api/protocol/v0/app-requests", AppRequestView.as_view(), name="app_requests"),
]
