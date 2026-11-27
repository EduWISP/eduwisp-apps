# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Michele Salerno e i contributori di EduWISP
from django.apps import AppConfig


class AppsConfig(AppConfig):
    name = "eduwisp_apps"
    verbose_name = "app consentite"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        from . import signals  # noqa: F401
