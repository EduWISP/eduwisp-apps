# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Michele Salerno e i contributori di EduWISP
"""Contributo alla policy del dispositivo (EDUWISP_POLICY_PROVIDERS in eduwisp-devices).

- ``blocked``: app vietate dalla piattaforma, sempre (anche senza elenco di app consentite).
- ``allowed``: con l'elenco attivo, catalogo della piattaforma + regole dell'istituto +
  sblocchi temporanei della classe; senza elenco, solo le app obbligatorie.
- ``required``: app obbligatorie decise dall'istituto (ADR-0019).
"""

from django.db.models import Q
from django.utils import timezone
from eduwisp_devices.models import DeviceAssignment

from .models import (
    AppPolicyState,
    AppRule,
    PlatformApp,
    PlatformCatalogVersion,
    PlatformStatus,
    RequiredApp,
    TemporaryUnlock,
)


def classe_del_dispositivo(device):
    a = (
        DeviceAssignment.objects.filter(device=device, ended_at__isnull=True)
        .select_related("school_class__section")
        .first()
    )
    return a.school_class if a else None


def _ambito(classe):
    q = Q(track__isnull=True, school_class__isnull=True)
    if classe is not None:
        q |= Q(school_class=classe)
        if classe.section.track_id:
            q |= Q(track_id=classe.section.track_id)
    return q


def _piattaforma(device, status):
    return set(
        PlatformApp.objects.filter(platform=device.platform, status=status).values_list(
            "identifier", flat=True
        )
    )


def required_apps(device, classe=None):
    return set(
        RequiredApp.objects.filter(
            _ambito(classe), organization=device.organization, platform=device.platform
        ).values_list("identifier", flat=True)
    )


def allowed_apps(device, now=None, vietate=None):
    """Elenco per il protocollo: [{"id": ...}, {"id": ..., "until": ...}, ...] (ADR-0019)."""
    now = now or timezone.now()
    vietate = _piattaforma(device, PlatformStatus.VIETATA) if vietate is None else vietate
    classe = classe_del_dispositivo(device)
    obbligatorie = required_apps(device, classe) - vietate
    sempre = (
        _piattaforma(device, PlatformStatus.CONSENTITA)
        | set(
            AppRule.objects.filter(
                _ambito(classe), organization=device.organization, app__platform=device.platform
            ).values_list("app__identifier", flat=True)
        )
        | obbligatorie
    ) - vietate
    elenco = [
        {"id": i, "required": True} if i in obbligatorie else {"id": i} for i in sorted(sempre)
    ]
    if classe is not None:
        scadenze = {}
        for s in TemporaryUnlock.objects.filter(
            school_class=classe,
            app__platform=device.platform,
            starts_at__lte=now,
            ends_at__gt=now,
            ended_early_at__isnull=True,
        ).select_related("app"):
            i = s.app.identifier
            if i not in sempre and i not in vietate:
                scadenze[i] = max(scadenze.get(i, s.ends_at), s.ends_at)
        elenco += [{"id": i, "until": t.isoformat()} for i, t in sorted(scadenze.items())]
    return elenco


def provide(device):
    stato = AppPolicyState.objects.filter(organization=device.organization).first()
    vietate = _piattaforma(device, PlatformStatus.VIETATA)
    catalogo = PlatformCatalogVersion.objects.filter(pk=1).first()
    versione = (stato.version if stato else 0) + (catalogo.version if catalogo else 0)
    if stato is not None and stato.allowlist_enabled:
        apps = {"mode": "allowlist", "allowed": allowed_apps(device, vietate=vietate)}
    else:
        obbligatorie = sorted(required_apps(device, classe_del_dispositivo(device)) - vietate)
        if not vietate and not obbligatorie:
            return None
        apps = {"mode": "blocklist", "allowed": [{"id": i, "required": True} for i in obbligatorie]}
    apps["blocked"] = sorted(vietate)
    return {"policy": {"apps": apps}, "version": versione}
