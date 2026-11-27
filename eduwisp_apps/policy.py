# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Michele Salerno e i contributori di EduWISP
"""Contributo alla policy del dispositivo (EDUWISP_POLICY_PROVIDERS in eduwisp-devices)."""

from django.db.models import Q
from django.utils import timezone
from eduwisp_devices.models import DeviceAssignment

from .models import AppPolicyState, AppRule, TemporaryUnlock


def classe_del_dispositivo(device):
    a = (
        DeviceAssignment.objects.filter(device=device, ended_at__isnull=True)
        .select_related("school_class__section")
        .first()
    )
    return a.school_class if a else None


def allowed_apps(device, now=None):
    """Elenco per il protocollo: [{"id": ...}, {"id": ..., "until": ...}] (ADR-0019)."""
    now = now or timezone.now()
    classe = classe_del_dispositivo(device)
    ambito = Q(track__isnull=True, school_class__isnull=True)
    if classe is not None:
        ambito |= Q(school_class=classe)
        if classe.section.track_id:
            ambito |= Q(track_id=classe.section.track_id)
    sempre = set(
        AppRule.objects.filter(
            ambito, organization=device.organization, app__platform=device.platform
        ).values_list("app__identifier", flat=True)
    )
    elenco = [{"id": i} for i in sorted(sempre)]
    if classe is not None:
        sblocchi = TemporaryUnlock.objects.filter(
            school_class=classe,
            app__platform=device.platform,
            starts_at__lte=now,
            ends_at__gt=now,
            ended_early_at__isnull=True,
        ).select_related("app")
        scadenze = {}
        for s in sblocchi:
            if s.app.identifier not in sempre:
                scadenze[s.app.identifier] = max(
                    scadenze.get(s.app.identifier, s.ends_at), s.ends_at
                )
        elenco += [{"id": i, "until": t.isoformat()} for i, t in sorted(scadenze.items())]
    return elenco


def provide(device):
    stato = AppPolicyState.objects.filter(organization=device.organization).first()
    if stato is None or not stato.allowlist_enabled:
        return None
    return {
        "policy": {"apps": {"mode": "allowlist", "allowed": allowed_apps(device)}},
        "version": stato.version,
    }
