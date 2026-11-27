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


class AppRuleInline(OrganizationScopedAdminMixin, admin.TabularInline):
    model = models.AppRule
    organization_roles = MANAGERS
    extra = 0
    fields = ["organization", "track", "school_class", "student", "required"]
    autocomplete_fields = ["student"]


@admin.register(models.App)
class AppAdmin(ScopedAdmin):
    """Elenco unico (ADR-0020): l'app, dove è consentita e se è obbligatoria."""

    list_display = ["name", "identifier", "platform", "con_apk", "organization"]
    search_fields = ["name", "identifier"]
    readonly_fields = ["apk_sha256", "apk_size"]
    inlines = [AppRuleInline]

    @admin.display(boolean=True, description="APK")
    def con_apk(self, obj):
        return bool(obj.apk)


@admin.register(models.AppRule)
class AppRuleAdmin(ScopedAdmin):
    list_display = ["app", "track", "school_class", "student", "required", "organization"]
    autocomplete_fields = ["app", "student"]
    list_editable = ["required"]
    list_filter = ["required", "track"]


@admin.register(models.TemporaryUnlock)
class TemporaryUnlockAdmin(ScopedAdmin):
    """Gli sblocchi si creano dal portale (docenti); qui solo consultazione."""

    list_display = ["app", "school_class", "teacher", "starts_at", "ends_at", "ended_early_at"]
    list_filter = ["school_class__section"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(models.PlatformApp)
class PlatformAppAdmin(admin.ModelAdmin):
    """Solo l'amministratore di sistema decide le app consentite o vietate ovunque."""

    list_display = ["name", "identifier", "category", "status", "platform"]
    list_filter = ["status", "category"]
    search_fields = ["name", "identifier"]

    def _solo_admin(self, request, obj=None):
        return request.user.is_active and request.user.is_superuser

    has_module_permission = _solo_admin
    has_view_permission = _solo_admin
    has_add_permission = _solo_admin
    has_change_permission = _solo_admin
    has_delete_permission = _solo_admin


class AppRequestOpinionInline(admin.TabularInline):
    model = models.AppRequestOpinion
    extra = 0
    can_delete = False
    readonly_fields = ["guardian", "reason", "created_at"]

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(models.AppRequest)
class AppRequestAdmin(ScopedAdmin):
    """Consultazione: le decisioni si prendono dal portale, con motivazione (ADR-0021)."""

    list_display = ["identifier", "name", "student", "school_class", "status", "created_at"]
    list_filter = ["status"]
    readonly_fields = [f.name for f in models.AppRequest._meta.fields]
    inlines = [AppRequestOpinionInline]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
