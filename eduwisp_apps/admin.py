# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Michele Salerno e i contributori di EduWISP
from django.contrib import admin
from eduwisp_users.models import Role
from eduwisp_users.tenancy import OrganizationScopedAdminMixin

from . import models

MANAGERS = [Role.SCHOOL_ADMIN, Role.IT_ADMIN]


class ScopedAdmin(OrganizationScopedAdminMixin, admin.ModelAdmin):
    organization_roles = MANAGERS


@admin.register(models.AppPolicyState)
class AppPolicyStateAdmin(ScopedAdmin):
    list_display = ["organization", "allowlist_enabled", "version"]


@admin.register(models.App)
class AppAdmin(ScopedAdmin):
    list_display = ["name", "identifier", "platform", "organization"]
    search_fields = ["name", "identifier"]


@admin.register(models.AppRule)
class AppRuleAdmin(ScopedAdmin):
    list_display = ["app", "track", "school_class", "organization"]
    list_filter = ["track"]
    autocomplete_fields = ["app"]


@admin.register(models.TemporaryUnlock)
class TemporaryUnlockAdmin(ScopedAdmin):
    """Gli sblocchi si creano dal portale (docenti); qui solo consultazione."""

    list_display = ["app", "school_class", "teacher", "starts_at", "ends_at", "ended_early_at"]
    list_filter = ["school_class__section"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
